"""
Servicios para detección y notificación push/bandeja de carritos abandonados (CU-26 / CU-27).
"""

from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.crm.models import CampanaCarrito, RegistroRecuperacionCarrito
from apps.marketing.models import Cupon, NotificacionEnviada
from apps.marketing.notificaciones import crear_notificacion
from apps.pedidos.models import Carrito, Pedido


def sincronizar_cupon_campana_carrito(campana: CampanaCarrito):
    """
    Si la campaña de carrito abandonado tiene un código promocional y porcentaje
    de descuento (> 0), asegura que exista un Cupón válido en la tienda para que
    el cliente pueda aplicarlo en su carrito.
    """
    codigo = (campana.codigo_cupon or '').strip().upper()
    if not codigo or campana.descuento_porcentaje <= 0:
        return None

    hoy = timezone.localdate()
    cupon = Cupon.objects.filter(tienda=campana.tienda, codigo__iexact=codigo).first()
    if cupon is None:
        cupon = Cupon.objects.create(
            tienda=campana.tienda,
            codigo=codigo,
            tipo_descuento='porcentaje',
            valor_descuento=Decimal(str(campana.descuento_porcentaje)),
            fecha_inicio=hoy,
            fecha_expiracion=hoy + timedelta(days=30),
            usos_maximos=1000,
            limite_por_cliente=1,
            activo=bool(campana.activo),
        )
    else:
        cupon.tipo_descuento = 'porcentaje'
        cupon.valor_descuento = Decimal(str(campana.descuento_porcentaje))
        if cupon.fecha_expiracion < hoy:
            cupon.fecha_expiracion = hoy + timedelta(days=30)
        cupon.activo = bool(campana.activo)
        cupon.save(update_fields=['tipo_descuento', 'valor_descuento', 'fecha_expiracion', 'activo'])
    return cupon


def construir_mensaje_carrito_push(campana: CampanaCarrito, productos_str: str) -> str:
    """Construye el texto de la notificación push incluyendo cupón si aplica."""
    base = (campana.mensaje_email or '').strip()
    partes = [base] if base else []
    codigo = (campana.codigo_cupon or '').strip().upper()
    if campana.descuento_porcentaje > 0 and codigo:
        partes.append(
            f'Usa el cupón {codigo} para obtener {campana.descuento_porcentaje}% de descuento.'
        )
    if productos_str:
        partes.append(f'Productos: {productos_str}')
    return ' '.join(partes)


def notificar_carritos_abandonados_tienda(
    campana: CampanaCarrito,
    *,
    incluir_recientes: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Evalúa los carritos de la tienda y envía notificaciones push/bandeja a los clientes.
    Si `incluir_recientes=True` (p. ej. al disparar prueba desde el panel), notifica
    carritos activos con ítems aunque aún no hayan cumplido las horas de inactividad.
    """
    if not campana.tienda.activa:
        return 0

    if not dry_run and campana.activo:
        sincronizar_cupon_campana_carrito(campana)

    limite = timezone.now() - timedelta(hours=campana.horas_inactividad)
    qs = Carrito.objects.filter(
        tienda=campana.tienda,
        cliente__is_active=True,
        cliente__activo=True,
    ).select_related('cliente')

    if not incluir_recientes:
        qs = qs.filter(ultima_actividad__lte=limite)

    total = 0
    for c in qs:
        if not c.items.exists():
            continue
        if Pedido.objects.filter(
            cliente=c.cliente,
            tienda=c.tienda,
            fecha__gte=c.ultima_actividad,
        ).exclude(estado_actual='cancelado').exists():
            continue

        clave = f'carrito:{c.pk}:{c.ultima_actividad.isoformat()}'
        if dry_run:
            total += int(not NotificacionEnviada.objects.filter(clave_evento=clave).exists())
            continue

        productos = ', '.join(
            c.items.values_list('variante__producto__nombre', flat=True)[:3]
        )
        with transaction.atomic():
            c_locked = Carrito.objects.select_for_update().get(pk=c.pk)
            if (not incluir_recientes and c_locked.ultima_actividad > limite) or not c_locked.items.exists():
                continue
            clave = f'carrito:{c_locked.pk}:{c_locked.ultima_actividad.isoformat()}'
            datos = {'carrito_id': c_locked.pk}
            codigo = (campana.codigo_cupon or '').strip().upper()
            if campana.descuento_porcentaje > 0 and codigo:
                datos['codigo_cupon'] = codigo
                datos['descuento_porcentaje'] = str(campana.descuento_porcentaje)

            _, creada = crear_notificacion(
                tienda=campana.tienda,
                cliente=c_locked.cliente,
                titulo=campana.asunto_email or f'¡Tienes productos esperándote en {campana.tienda.nombre}!',
                mensaje=construir_mensaje_carrito_push(campana, productos),
                tipo='carrito_abandonado',
                datos=datos,
                clave=clave,
            )
            if creada and not RegistroRecuperacionCarrito.objects.filter(
                campana=campana,
                carrito=c_locked,
                fecha_envio__gte=c_locked.ultima_actividad,
            ).exists():
                RegistroRecuperacionCarrito.objects.create(
                    campana=campana,
                    carrito=c_locked,
                    cliente=c_locked.cliente,
                    correo_enviado=False,
                )
            total += int(creada)
    return total


def verificar_carritos_abandonados_cliente(cliente) -> int:
    """
    Verifica si el cliente autenticado tiene carritos que ya superaron el umbral
    de inactividad en tiendas con campaña activa y genera su notificación push/bandeja.
    """
    if not getattr(cliente, 'is_authenticated', False):
        return 0

    total = 0
    carritos = (
        Carrito.objects.filter(cliente=cliente, tienda__activa=True)
        .select_related('tienda')
        .prefetch_related('items')
    )
    for carrito in carritos:
        if not carrito.items.exists():
            continue
        campana = CampanaCarrito.objects.filter(tienda=carrito.tienda, activo=True).first()
        if not campana:
            continue
        limite = timezone.now() - timedelta(hours=campana.horas_inactividad)
        if carrito.ultima_actividad <= limite:
            total += notificar_carritos_abandonados_tienda(campana)
    return total

