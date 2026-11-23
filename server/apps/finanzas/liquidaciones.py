"""Servicios de dominio para suscripciones de tiendas y liquidación de ventas (CU-37)."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Optional

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.pedidos.models import Pedido
from apps.tiendas.models import Tienda
from apps.usuarios.audit import ACCION_ACTUALIZAR, ACCION_CREAR, registrar_auditoria, snapshot_instancia

from .models import LiquidacionTienda, PlanSuscripcion, SuscripcionTienda

ESTADOS_PEDIDO_LIQUIDABLES = ('pagado', 'confirmado', 'en_camino', 'entregado')
COMISION_POR_DEFECTO = Decimal('5.00')
CIEN = Decimal('100.00')


class ErrorLiquidacion(ValueError):
    """Error de regla de negocio en el cálculo o transición de una liquidación."""


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _auditar(usuario, accion: str, tabla: str, registro_id: int,
             datos_anteriores=None, datos_nuevos=None) -> None:
    registrar_auditoria(
        SimpleNamespace(user=usuario),
        accion,
        tabla=tabla,
        registro_id=registro_id,
        datos_anteriores=datos_anteriores,
        datos_nuevos=datos_nuevos,
    )


def suscripcion_vigente_de_tienda(tienda: Tienda) -> Optional[SuscripcionTienda]:
    """Devuelve la suscripción activa o en prueba más reciente de una tienda."""
    return (
        SuscripcionTienda.objects.select_related('plan')
        .filter(tienda=tienda, estado__in=(SuscripcionTienda.Estado.ACTIVA, SuscripcionTienda.Estado.PRUEBA))
        .order_by('-fecha_fin', '-id')
        .first()
    )


def comision_vigente_para_tienda(tienda: Tienda) -> Decimal:
    """Obtiene el porcentaje de comisión aplicable según el plan vigente de la tienda."""
    susc = suscripcion_vigente_de_tienda(tienda)
    if susc and susc.plan_id:
        return susc.plan.comision_porcentaje
    return COMISION_POR_DEFECTO


def calcular_totales_periodo(
    tienda: Tienda,
    periodo_inicio: date,
    periodo_fin: date,
) -> dict:
    """Calcula pedidos liquidables, ventas brutas, comisión de plataforma y neto a transferir."""
    if periodo_inicio > periodo_fin:
        raise ErrorLiquidacion('La fecha inicial no puede ser posterior a la fecha final.')

    qs = Pedido.objects.filter(
        tienda=tienda,
        estado_actual__in=ESTADOS_PEDIDO_LIQUIDABLES,
        fecha__date__gte=periodo_inicio,
        fecha__date__lte=periodo_fin,
    )
    agregado = qs.aggregate(total=Sum('total'))
    cantidad_pedidos = qs.count()
    total_ventas = _redondear(Decimal(str(agregado['total'] or '0.00')))
    comision_pct = comision_vigente_para_tienda(tienda)
    monto_comision = _redondear((total_ventas * comision_pct) / CIEN)
    monto_neto = _redondear(total_ventas - monto_comision)

    return {
        'tienda_id': tienda.id,
        'tienda_nombre': tienda.nombre,
        'periodo_inicio': periodo_inicio,
        'periodo_fin': periodo_fin,
        'cantidad_pedidos': cantidad_pedidos,
        'total_ventas': total_ventas,
        'comision_porcentaje': comision_pct,
        'monto_comision': monto_comision,
        'monto_neto': monto_neto,
    }


@transaction.atomic
def generar_liquidacion_tienda(
    *,
    tienda: Tienda,
    periodo_inicio: date,
    periodo_fin: date,
    usuario,
    notas: str = '',
) -> LiquidacionTienda:
    """Genera una liquidación formal verificando que no exista otra activa para el mismo periodo."""
    resumen = calcular_totales_periodo(tienda, periodo_inicio, periodo_fin)

    solapada = (
        LiquidacionTienda.objects.select_for_update()
        .filter(
            tienda=tienda,
            periodo_inicio__lte=periodo_fin,
            periodo_fin__gte=periodo_inicio,
        )
        .exclude(estado=LiquidacionTienda.Estado.ANULADA)
        .first()
    )
    if solapada is not None:
        raise ErrorLiquidacion(
            f'Ya existe la liquidación #{solapada.id} ({solapada.estado}) que cubre fechas de ese periodo.'
        )

    liquidacion = LiquidacionTienda.objects.create(
        tienda=tienda,
        periodo_inicio=periodo_inicio,
        periodo_fin=periodo_fin,
        cantidad_pedidos=resumen['cantidad_pedidos'],
        total_ventas=resumen['total_ventas'],
        comision_porcentaje=resumen['comision_porcentaje'],
        monto_comision=resumen['monto_comision'],
        monto_neto=resumen['monto_neto'],
        estado=LiquidacionTienda.Estado.PENDIENTE,
        notas=notas.strip(),
        generado_por=usuario,
    )
    _auditar(
        usuario,
        ACCION_CREAR,
        'liquidacion_tienda',
        liquidacion.id,
        datos_nuevos=snapshot_instancia(liquidacion),
    )
    return liquidacion


@transaction.atomic
def transicionar_liquidacion(
    *,
    liquidacion: LiquidacionTienda,
    accion: str,
    usuario,
    referencia_pago: str = '',
    notas: str = '',
) -> LiquidacionTienda:
    """Aplica transiciones válidas (aprobar, pagar, anular) con trazabilidad en bitácora."""
    anterior = snapshot_instancia(liquidacion)

    if accion == 'aprobar':
        if liquidacion.estado != LiquidacionTienda.Estado.PENDIENTE:
            raise ErrorLiquidacion('Solo se pueden aprobar liquidaciones en estado pendiente.')
        liquidacion.estado = LiquidacionTienda.Estado.APROBADA
    elif accion == 'pagar':
        if liquidacion.estado not in (
            LiquidacionTienda.Estado.PENDIENTE,
            LiquidacionTienda.Estado.APROBADA,
        ):
            raise ErrorLiquidacion('Esta liquidación no admite registro de pago en su estado actual.')
        ref = referencia_pago.strip()
        if not ref:
            raise ErrorLiquidacion('Debe indicar la referencia o comprobante de transferencia.')
        liquidacion.estado = LiquidacionTienda.Estado.PAGADA
        liquidacion.referencia_pago = ref
        liquidacion.pagado_en = timezone.now()
    elif accion == 'anular':
        if liquidacion.estado == LiquidacionTienda.Estado.PAGADA:
            raise ErrorLiquidacion('No se puede anular una liquidación que ya fue pagada.')
        if liquidacion.estado == LiquidacionTienda.Estado.ANULADA:
            raise ErrorLiquidacion('La liquidación ya se encuentra anulada.')
        liquidacion.estado = LiquidacionTienda.Estado.ANULADA
    else:
        raise ErrorLiquidacion(f'Acción de liquidación no soportada: {accion}.')

    if notas.strip():
        liquidacion.notas = notas.strip()

    liquidacion.save()
    _auditar(
        usuario,
        ACCION_ACTUALIZAR,
        'liquidacion_tienda',
        liquidacion.id,
        datos_anteriores=anterior,
        datos_nuevos=snapshot_instancia(liquidacion),
    )
    return liquidacion


@transaction.atomic
def asignar_suscripcion_a_tienda(
    *,
    tienda: Tienda,
    plan: PlanSuscripcion,
    estado: str,
    fecha_inicio: date,
    fecha_fin: date,
    auto_renovar: bool,
    usuario,
) -> SuscripcionTienda:
    """Asigna o actualiza el plan de suscripción de una tienda con registro en bitácora."""
    if not plan.activo and estado in (SuscripcionTienda.Estado.ACTIVA, SuscripcionTienda.Estado.PRUEBA):
        raise ErrorLiquidacion(f'El plan "{plan.nombre}" está inactivo y no puede asignarse.')
    if fecha_inicio > fecha_fin:
        raise ErrorLiquidacion('La fecha de inicio de suscripción no puede ser posterior a la fecha de fin.')

    suscripcion = SuscripcionTienda.objects.create(
        tienda=tienda,
        plan=plan,
        estado=estado,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        auto_renovar=auto_renovar,
    )
    _auditar(
        usuario,
        ACCION_CREAR,
        'suscripcion_tienda',
        suscripcion.id,
        datos_nuevos=snapshot_instancia(suscripcion),
    )
    return suscripcion
