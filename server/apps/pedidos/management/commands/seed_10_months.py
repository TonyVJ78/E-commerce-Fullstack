"""
Management Command para Kantu Market: Sembrado integral de 10 meses de operación real.

Genera datos sintéticos coherentes e idempotentes desde hace 10 meses hasta hoy,
con curva de crecimiento orgánica (menor actividad inicial y mayor volumen en los
últimos 3 meses), cubriendo todos los módulos y casos de uso del sistema.

Uso:
    python manage.py seed_10_months
    python manage.py seed_10_months --purge
"""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto, Variante, VarianteStockMovimiento
from apps.crm.models import (
    CampanaCarrito,
    FichaCliente,
    InteraccionCliente,
    ItemListaDeseos,
    ListaDeseos,
    MensajeTicket,
    ReglaSegmentacion,
    RegistroRecuperacionCarrito,
    Segmento,
    SegmentoCliente,
    TicketSoporte,
)
from apps.crm.services.segmentacion_service import recalcular_segmentos_tienda
from apps.finanzas.models import (
    GastoOperativo,
    LiquidacionTienda,
    PlanSuscripcion,
    SuscripcionTienda,
    TipoCambio,
)
from apps.ia.models import EventoUsuario, ModeloML, Recomendacion, ReporteGenerado
from apps.marketing.models import Campana, Cupon, CuponUso, NotificacionEnviada
from apps.pedidos.models import (
    Carrito,
    DireccionEnvio,
    Envio,
    HistorialEstadoPedido,
    ItemCarrito,
    ItemPedido,
    MetodoPago,
    Pago,
    Pedido,
    Resena,
)
from apps.tiendas.models import DireccionTienda, Tienda, UsuarioTienda
from apps.usuarios.models import BitacoraAcceso, LogAuditoria, Permiso, Rol, RolPermiso, Usuario

PASSWORD_DEMO = 'Kantu2026!'
PESOS_MESES = [3, 4, 5, 6, 8, 10, 12, 16, 18, 22]


@contextmanager
def fechas_explicitas():
    """Desactiva temporalmente auto_now_add/auto_now para sembrar fechas históricas."""
    modelos = [
        (Usuario, ['fecha_registro']),
        (Producto, ['creado', 'actualizado']),
        (VarianteStockMovimiento, ['created_at']),
        (Pedido, ['fecha']),
        (HistorialEstadoPedido, ['fecha']),
        (Pago, ['fecha']),
        (Resena, ['fecha']),
        (Carrito, ['fecha_creacion']),
        (TicketSoporte, ['fecha_creacion', 'fecha_actualizacion']),
        (MensajeTicket, ['fecha_envio']),
        (InteraccionCliente, ['fecha']),
        (ListaDeseos, ['fecha_creacion']),
        (RegistroRecuperacionCarrito, ['fecha_envio']),
        (CuponUso, ['fecha_uso']),
        (NotificacionEnviada, ['fecha']),
        (EventoUsuario, ['fecha']),
        (Recomendacion, ['fecha_generada']),
        (ReporteGenerado, ['fecha_generacion']),
        (BitacoraAcceso, ['fecha']),
        (LogAuditoria, ['fecha']),
    ]
    respaldo = []
    try:
        for modelo, campos in modelos:
            for nombre in campos:
                campo = modelo._meta.get_field(nombre)
                respaldo.append((campo, campo.auto_now, campo.auto_now_add))
                campo.auto_now = False
                campo.auto_now_add = False
        yield
    finally:
        for campo, auto_now, auto_now_add in respaldo:
            campo.auto_now = auto_now
            campo.auto_now_add = auto_now_add


def _q2(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = 'Puebla 10 meses de operación continua y coherente para todos los casos de uso de Kantu Market.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--purge',
            action='store_true',
            help='Limpia primero los datos operativos/demo en orden de dependencia antes de sembrar.',
        )
        parser.add_argument(
            '--pedidos',
            type=int,
            default=180,
            help='Cantidad aproximada de pedidos distribuidos en 10 meses (default: 180).',
        )
        parser.add_argument(
            '--eventos',
            type=int,
            default=420,
            help='Cantidad de eventos de telemetría IA a generar (default: 420).',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=2026,
            help='Semilla aleatoria reproducible (default: 2026).',
        )

    def handle(self, *args, **options):
        rng = random.Random(options['seed'])
        ahora = timezone.now()
        hoy = timezone.localdate()
        inicio_10m = ahora - timedelta(days=300)

        if options['purge']:
            self.stdout.write(self.style.WARNING('>>> Purgando datos previos en orden referencial...'))
            self._purgar_base()

        # Idempotencia si ya existe el lote seed_10_months sin --purge
        if not options['purge'] and Tienda.objects.filter(slug='kantu-alpaca-couture').exists() and Pedido.objects.count() >= 50:
            self.stdout.write(
                self.style.SUCCESS(
                    'La base ya contiene los datos sembrados de 10 meses. Usa --purge para regenerar desde cero.'
                )
            )
            self._imprimir_credenciales()
            return

        with transaction.atomic(), fechas_explicitas():
            roles = self._sembrar_roles_y_permisos()
            usuarios = self._sembrar_usuarios(roles, inicio_10m, ahora)
            self._sembrar_tipos_cambio(hoy)
            planes = self._sembrar_planes()
            tiendas = self._sembrar_tiendas_y_suscripciones(usuarios, planes, hoy)
            catalogo = self._sembrar_catalogo(tiendas, usuarios, inicio_10m)
            metodos_pago = self._sembrar_metodos_pago()
            cupones = self._sembrar_marketing(tiendas, hoy)
            direcciones = self._sembrar_direcciones_envio(tiendas, usuarios['clientes'])

            pedidos_creados = self._sembrar_pedidos_y_postventa(
                rng=rng,
                total_pedidos=options['pedidos'],
                tiendas=tiendas,
                clientes=usuarios['clientes'],
                catalogo=catalogo,
                metodos_pago=metodos_pago,
                direcciones=direcciones,
                cupones=cupones,
                ahora=ahora,
            )
            self._sembrar_finanzas_mensuales(tiendas, usuarios['admin'], hoy)
            self._sembrar_crm_tickets_carritos(
                rng=rng,
                tiendas=tiendas,
                clientes=usuarios['clientes'],
                catalogo=catalogo,
                pedidos=pedidos_creados,
                ahora=ahora,
            )
            self._sembrar_ia_y_auditoria(
                rng=rng,
                total_eventos=options['eventos'],
                tiendas=tiendas,
                clientes=usuarios['clientes'],
                catalogo=catalogo,
                usuarios=usuarios,
                ahora=ahora,
            )

        self.stdout.write(self.style.SUCCESS('[OK] Sembrado de 10 meses completado con éxito.'))
        self._imprimir_credenciales()

    def _purgar_base(self):
        with transaction.atomic():
            for modelo in (
                CuponUso,
                NotificacionEnviada,
                Cupon,
                Campana,
                RegistroRecuperacionCarrito,
                CampanaCarrito,
                MensajeTicket,
                TicketSoporte,
                InteraccionCliente,
                ItemListaDeseos,
                ListaDeseos,
                SegmentoCliente,
                ReglaSegmentacion,
                FichaCliente,
                Segmento,
                Envio,
                Pago,
                HistorialEstadoPedido,
                ItemPedido,
                Pedido,
                ItemCarrito,
                Carrito,
                Resena,
                DireccionEnvio,
                VarianteStockMovimiento,
                Variante,
                Producto,
                Categoria,
                LiquidacionTienda,
                SuscripcionTienda,
                GastoOperativo,
                EventoUsuario,
                Recomendacion,
                ReporteGenerado,
                ModeloML,
                LogAuditoria,
                BitacoraAcceso,
                DireccionTienda,
                UsuarioTienda,
                Tienda,
            ):
                modelo.objects.all().delete()

    def _fecha_organica(self, rng: random.Random, ahora: datetime) -> datetime:
        """Elige una fecha en los últimos 300 días siguiendo la curva de crecimiento de 10 meses."""
        mes_idx = rng.choices(range(10), weights=PESOS_MESES, k=1)[0]
        dias_atras_inicio = (9 - mes_idx) * 30
        dia_offset = rng.uniform(0, 29.8)
        dt = ahora - timedelta(days=dias_atras_inicio + dia_offset)
        return dt.replace(
            hour=rng.randint(8, 22),
            minute=rng.randint(0, 59),
            second=rng.randint(0, 59),
            microsecond=0,
        )

    def _sembrar_roles_y_permisos(self) -> dict:
        rol_admin, _ = Rol.objects.get_or_create(nombre='administrador')
        rol_empresa, _ = Rol.objects.get_or_create(nombre='empresa')
        rol_cliente, _ = Rol.objects.get_or_create(nombre='cliente')

        permisos_base = [
            ('gestionar_plataforma', 'Administrar planes, usuarios, auditoría y liquidaciones'),
            ('gestionar_tienda', 'Administrar catálogo, pedidos, gastos y clientes de tienda'),
            ('comprar_catalogo', 'Realizar compras, reseñas y tickets de soporte'),
        ]
        for cod, nombre in permisos_base:
            perm, _ = Permiso.objects.get_or_create(codigo=cod, defaults={'nombre': nombre})
            RolPermiso.objects.get_or_create(rol=rol_admin, permiso=perm)
            if cod == 'gestionar_tienda':
                RolPermiso.objects.get_or_create(rol=rol_empresa, permiso=perm)
            if cod == 'comprar_catalogo':
                RolPermiso.objects.get_or_create(rol=rol_cliente, permiso=perm)

        return {'administrador': rol_admin, 'empresa': rol_empresa, 'cliente': rol_cliente}

    def _upsert_usuario(self, email: str, first_name: str, last_name: str, rol: Rol,
                        fecha_registro: datetime, superuser: bool = False) -> Usuario:
        usuario = Usuario.objects.filter(email=email).first()
        if usuario is None:
            usuario = Usuario(
                email=email,
                first_name=first_name,
                last_name=last_name,
                rol=rol,
                activo=True,
                is_active=True,
                is_staff=superuser,
                is_superuser=superuser,
                fecha_registro=fecha_registro,
            )
            usuario.set_password(PASSWORD_DEMO)
            usuario.save()
        else:
            usuario.first_name = first_name
            usuario.last_name = last_name
            usuario.rol = rol
            usuario.activo = True
            usuario.is_active = True
            usuario.is_staff = superuser
            usuario.is_superuser = superuser
            usuario.set_password(PASSWORD_DEMO)
            usuario.save()
        return usuario

    def _sembrar_usuarios(self, roles: dict, inicio_10m: datetime, ahora: datetime) -> dict:
        admin = self._upsert_usuario(
            'admin@kantu.bo', 'Gustavo', 'Sandoval', roles['administrador'], inicio_10m, superuser=True
        )
        empresas = [
            self._upsert_usuario('empresa1@kantu.bo', 'Maria', 'Condori', roles['empresa'], inicio_10m + timedelta(days=2)),
            self._upsert_usuario('empresa2@kantu.bo', 'Carlos', 'Mamani', roles['empresa'], inicio_10m + timedelta(days=45)),
            self._upsert_usuario('empresa3@kantu.bo', 'Lucía', 'Quispe', roles['empresa'], ahora - timedelta(days=75)),
        ]
        nombres_clientes = [
            ('cliente1@kantu.bo', 'Sofía', 'Torrez', 5),
            ('cliente2@kantu.bo', 'Mateo', 'Vargas', 18),
            ('cliente3@kantu.bo', 'Valeria', 'Rojas', 40),
            ('cliente4@kantu.bo', 'Diego', 'Choque', 65),
            ('cliente5@kantu.bo', 'Camila', 'Paredes', 95),
            ('cliente6@kantu.bo', 'Sebastián', 'Flores', 130),
            ('cliente7@kantu.bo', 'Andrea', 'Mendoza', 175),
            ('cliente8@kantu.bo', 'Alejandro', 'Salazar', 210),
            ('cliente9@kantu.bo', 'Fernanda', 'Gutiérrez', 245),
            ('cliente10@kantu.bo', 'Nicolás', 'Arce', 275),
        ]
        clientes = [
            self._upsert_usuario(email, fn, ln, roles['cliente'], inicio_10m + timedelta(days=dias))
            for email, fn, ln, dias in nombres_clientes
        ]
        return {'admin': admin, 'empresas': empresas, 'clientes': clientes}

    def _sembrar_tipos_cambio(self, hoy: date):
        tasas = [
            (hoy - timedelta(days=180), Decimal('11.4500'), 'BCB Histórico'),
            (hoy - timedelta(days=90), Decimal('11.6200'), 'BCB Histórico'),
            (hoy - timedelta(days=30), Decimal('11.7000'), 'BCB Histórico'),
            (hoy, Decimal('11.7500'), 'BCB Referencial'),
        ]
        for fecha_tc, usd_bob, fuente in tasas:
            TipoCambio.objects.update_or_create(
                fecha=fecha_tc,
                defaults={'usd_bob': usd_bob, 'fuente': fuente},
            )

    def _sembrar_planes(self) -> dict:
        estandar, _ = PlanSuscripcion.objects.update_or_create(
            codigo='estandar',
            defaults={
                'nombre': 'Plan Estándar',
                'descripcion': 'Ideal para emprendedores y marcas en crecimiento. Hasta 3 tiendas.',
                'precio_mensual': Decimal('99.00'),
                'comision_porcentaje': Decimal('8.00'),
                'max_tiendas': 3,
                'max_productos': 100,
                'max_usuarios': 5,
                'activo': True,
            },
        )
        premium, _ = PlanSuscripcion.objects.update_or_create(
            codigo='premium',
            defaults={
                'nombre': 'Plan Premium',
                'descripcion': 'Para empresas multi-sucursal con comisión preferencial y hasta 10 tiendas.',
                'precio_mensual': Decimal('249.00'),
                'comision_porcentaje': Decimal('5.00'),
                'max_tiendas': 10,
                'max_productos': 1000,
                'max_usuarios': 25,
                'activo': True,
            },
        )
        return {'estandar': estandar, 'premium': premium}

    def _sembrar_tiendas_y_suscripciones(self, usuarios: dict, planes: dict, hoy: date) -> list:
        empresas = usuarios['empresas']
        specs = [
            (
                empresas[0],
                'Kantu Alpaca Couture',
                'kantu-alpaca-couture',
                'Prendas exclusivas tejidas en fibra de alpaca real boliviana.',
                '#C8102E',
                planes['premium'],
                SuscripcionTienda.Estado.ACTIVA,
                'La Paz',
                'Av. Montenegro #1420, San Miguel',
            ),
            (
                empresas[0],
                'Andes Urban Wear',
                'andes-urban-wear',
                'Moda urbana contemporánea con identidad andina.',
                '#1E3A8A',
                planes['premium'],
                SuscripcionTienda.Estado.ACTIVA,
                'Santa Cruz',
                'Equipetrol Norte, Calle 7 #310',
            ),
            (
                empresas[1],
                'Titicaca Artesanías',
                'titicaca-artesanias',
                'Textiles, aguayos y accesorios elaborados a mano.',
                '#047857',
                planes['estandar'],
                SuscripcionTienda.Estado.ACTIVA,
                'Cochabamba',
                'Av. América #890, Zona Norte',
            ),
            (
                empresas[2],
                'Salar Diseño & Hogar',
                'salar-diseno-hogar',
                'Decoración textil y mantas de diseño boliviano.',
                '#B45309',
                planes['estandar'],
                SuscripcionTienda.Estado.PRUEBA,
                'La Paz',
                'Sopocachi, Calle Ecuador #455',
            ),
        ]
        tiendas = []
        for propietario, nombre, slug, desc, color, plan, estado, ciudad, direccion in specs:
            tienda, _ = Tienda.objects.update_or_create(
                slug=slug,
                defaults={
                    'propietario': propietario,
                    'nombre': nombre,
                    'descripcion': desc,
                    'color_primario': color,
                    'activa': True,
                },
            )
            UsuarioTienda.objects.get_or_create(
                usuario=propietario,
                tienda=tienda,
                defaults={'rol_interno': 'propietario'},
            )
            DireccionTienda.objects.get_or_create(
                tienda=tienda,
                ciudad=ciudad,
                defaults={'direccion': direccion, 'telefono': '+591 71543210'},
            )
            SuscripcionTienda.objects.get_or_create(
                tienda=tienda,
                plan=plan,
                estado=estado,
                defaults={
                    'fecha_inicio': hoy - timedelta(days=20),
                    'fecha_fin': hoy + timedelta(days=10),
                    'auto_renovar': True,
                },
            )
            tiendas.append(tienda)
        return tiendas

    def _sembrar_catalogo(self, tiendas: list, usuarios: dict, inicio_10m: datetime) -> list:
        productos_por_tienda = {
            'kantu-alpaca-couture': [
                ('Abrigos', 'Abrigo Illimani de Alpaca', '390.00', '33.19', '210.00', ['alpaca', 'invierno', 'premium']),
                ('Abrigos', 'Poncho Ceremonial Andino', '310.00', '26.38', '165.00', ['poncho', 'alpaca', 'artesanal']),
                ('Chompas', 'Chompa Tejida Nevado', '240.00', '20.43', '125.00', ['chompa', 'lana', 'invierno']),
                ('Accesorios', 'Chaleco Ejecutivo Altiplano', '220.00', None, '115.00', ['chaleco', 'formal']),
                ('Accesorios', 'Bufanda Suave Baby Alpaca', '120.00', '10.21', '55.00', ['bufanda', 'regalo']),
            ],
            'andes-urban-wear': [
                ('Chaquetas', 'Chaqueta Bomber Kantuta', '280.00', '23.83', '150.00', ['urbano', 'chaqueta']),
                ('Poleras', 'Polera Oversize Sajama', '135.00', None, '68.00', ['algodon', 'urbano']),
                ('Pantalones', 'Jogger Cargo Uyuni', '195.00', '16.60', '98.00', ['jogger', 'casual']),
                ('Sudaderas', 'Hoodie Tricolor Edición Limitada', '230.00', None, '120.00', ['hoodie', 'unisex']),
            ],
            'titicaca-artesanias': [
                ('Textiles', 'Manta Aguayo Tradicional', '180.00', '15.32', '90.00', ['aguayo', 'tradicional']),
                ('Accesorios', 'Mochila Étnica Copacabana', '160.00', None, '82.00', ['mochila', 'viaje']),
                ('Accesorios', 'Gorro Chullo Artesanal', '75.00', None, '35.00', ['chullo', 'invierno']),
                ('Textiles', 'Camino de Mesa Telar Real', '145.00', None, '70.00', ['hogar', 'telar']),
            ],
            'salar-diseno-hogar': [
                ('Hogar', 'Manta Nórdica Salar Blanco', '260.00', '22.13', '135.00', ['hogar', 'manta']),
                ('Hogar', 'Set de Cojines Andinos (x2)', '150.00', None, '75.00', ['cojin', 'decoracion']),
                ('Hogar', 'Tapiz Geométrico Tiwanaku', '210.00', None, '105.00', ['tapiz', 'arte']),
            ],
        }
        variantes_todas = []
        for idx_t, tienda in enumerate(tiendas):
            specs = productos_por_tienda.get(tienda.slug, [])
            for idx_p, (cat_nombre, prod_nombre, precio, precio_usd, costo, tags) in enumerate(specs, start=1):
                cat, _ = Categoria.objects.get_or_create(tienda=tienda, nombre=cat_nombre)
                slug = f'{tienda.slug}-prod-{idx_p}'
                prod, _ = Producto.objects.get_or_create(
                    tienda=tienda,
                    slug=slug,
                    defaults={
                        'categoria': cat,
                        'nombre': prod_nombre,
                        'descripcion': f'{prod_nombre} confeccionado con materiales seleccionados de alta durabilidad.',
                        'etiquetas': tags,
                        'imagenes': [],
                        'activo': True,
                        'creado': inicio_10m + timedelta(days=idx_t * 15 + idx_p * 3),
                        'actualizado': inicio_10m + timedelta(days=idx_t * 15 + idx_p * 3),
                    },
                )
                for talla in ('S/M', 'L/XL'):
                    sku = f'KM-{tienda.id}-{idx_p}-{talla[:1]}'
                    var, creado = Variante.objects.get_or_create(
                        producto=prod,
                        sku=sku,
                        defaults={
                            'nombre': f'Talla {talla}',
                            'precio': Decimal(precio),
                            'precio_usd': Decimal(precio_usd) if precio_usd else None,
                            'costo_unitario': Decimal(costo),
                            'stock': 800,
                            'stock_minimo': 15,
                            'atributos': {'talla': talla},
                            'activa': True,
                        },
                    )
                    if creado:
                        VarianteStockMovimiento.objects.create(
                            variante=var,
                            previous_stock=0,
                            delta=800,
                            resulting_stock=800,
                            actor=tienda.propietario,
                            reason='Stock inicial de apertura de temporada',
                            created_at=prod.creado,
                        )
                    variantes_todas.append(var)
        return variantes_todas

    def _sembrar_metodos_pago(self) -> list:
        nombres = [
            'Stripe / Tarjeta de Crédito',
            'QR Simple (BCP / BNB / Mercantil)',
            'Pago Contra Entrega',
        ]
        return [MetodoPago.objects.get_or_create(nombre=n, defaults={'activo': True})[0] for n in nombres]

    def _sembrar_marketing(self, tiendas: list, hoy: date) -> dict:
        cupones_por_tienda = {}
        for idx, tienda in enumerate(tiendas):
            camp, _ = Campana.objects.get_or_create(
                tienda=tienda,
                nombre=f'Campaña Temporada {tienda.nombre}',
                defaults={
                    'tipo': 'descuento_estacional',
                    'mensaje': 'Aprovecha descuentos especiales en colección seleccionada.',
                    'fecha_inicio': hoy - timedelta(days=120),
                    'fecha_fin': hoy + timedelta(days=45),
                },
            )
            cupon, _ = Cupon.objects.get_or_create(
                tienda=tienda,
                codigo=f'KANTU{10 + idx * 5}',
                defaults={
                    'campana': camp,
                    'tipo_descuento': 'porcentaje',
                    'valor_descuento': Decimal('10.00'),
                    'fecha_inicio': hoy - timedelta(days=90),
                    'fecha_expiracion': hoy + timedelta(days=60),
                    'usos_maximos': 500,
                    'monto_minimo': Decimal('100.00'),
                    'limite_por_cliente': 5,
                    'activo': True,
                },
            )
            cupones_por_tienda[tienda.id] = cupon
        return cupones_por_tienda

    def _sembrar_direcciones_envio(self, tiendas: list, clientes: list) -> dict:
        ciudades = ['La Paz', 'Santa Cruz', 'Cochabamba', 'Sucre', 'Tarija']
        mapa = {}
        for tienda in tiendas:
            for idx, cliente in enumerate(clientes):
                d, _ = DireccionEnvio.objects.get_or_create(
                    tienda=tienda,
                    cliente=cliente,
                    defaults={
                        'direccion': f'Av. Principal #{120 + idx * 17}',
                        'ciudad': ciudades[idx % len(ciudades)],
                        'referencia': 'Edificio residencial, planta baja',
                        'es_predeterminada': True,
                    },
                )
                mapa[(tienda.id, cliente.id)] = d
        return mapa

    def _sembrar_pedidos_y_postventa(
        self,
        *,
        rng: random.Random,
        total_pedidos: int,
        tiendas: list,
        clientes: list,
        catalogo: list,
        metodos_pago: list,
        direcciones: dict,
        cupones: dict,
        ahora: datetime,
    ) -> list:
        variantes_por_tienda = {}
        for var in catalogo:
            variantes_por_tienda.setdefault(var.producto.tienda_id, []).append(var)

        estados_dist = ['entregado'] * 55 + ['en_camino'] * 12 + ['confirmado'] * 10 + ['pagado'] * 10 + ['pendiente'] * 7 + ['cancelado'] * 6
        comentarios_ok = [
            (5, 'Excelente calidad, llegó antes de lo esperado y el acabado es impecable.'),
            (5, 'Muy buena tela y calce perfecto. Volveré a comprar sin duda.'),
            (4, 'Buen producto y atención rápida, el empaque llegó muy bien cuidado.'),
        ]
        comentarios_mix = [
            (3, 'El producto cumple, aunque el envío tardó un día más de lo previsto.'),
            (2, 'La talla era un poco justa respecto a la guía, pero me ayudaron con el cambio.'),
        ]

        pedidos = []
        for i in range(total_pedidos):
            # Clientes 0..2 compran con mayor frecuencia para poblar segmentos ALTO_VALOR y FRECUENTE
            if rng.random() < 0.48:
                cliente = rng.choice(clientes[:3])
            else:
                cliente = rng.choice(clientes[3:])

            tienda = rng.choices(tiendas, weights=[40, 28, 20, 12], k=1)[0]
            fecha_ped = self._fecha_organica(rng, ahora)
            estado = rng.choice(estados_dist)
            # Pedidos recientes tienen más probabilidad de estar pendientes/en camino
            if (ahora - fecha_ped).days < 5 and estado == 'entregado' and rng.random() < 0.5:
                estado = rng.choice(['pendiente', 'pagado', 'en_camino'])

            vars_t = variantes_por_tienda[tienda.id]
            elegidas = rng.sample(vars_t, k=min(rng.randint(1, 3), len(vars_t)))

            subtotal = Decimal('0.00')
            items_data = []
            for var in elegidas:
                cant = rng.randint(1, 3)
                precio_u = var.precio
                sub_item = _q2(precio_u * cant)
                subtotal += sub_item
                items_data.append((var, cant, precio_u, var.costo_unitario, sub_item))

            descuento = Decimal('0.00')
            cupon_usado = None
            if subtotal >= Decimal('150.00') and rng.random() < 0.22:
                cupon_usado = cupones[tienda.id]
                descuento = _q2(subtotal * Decimal('0.10'))
            total = _q2(subtotal - descuento)

            pedido = Pedido.objects.create(
                cliente=cliente,
                tienda=tienda,
                estado_actual=estado,
                fecha=fecha_ped,
                subtotal=subtotal,
                total=total,
                tipo_cambio_usd=Decimal('11.7500'),
            )
            for var, cant, precio_u, costo_u, _sub_item in items_data:
                ItemPedido.objects.create(
                    tienda=tienda,
                    pedido=pedido,
                    variante=var,
                    cantidad=cant,
                    precio_unitario=precio_u,
                    costo_unitario=costo_u,
                )

            if cupon_usado is not None:
                CuponUso.objects.create(
                    tienda=tienda,
                    cupon=cupon_usado,
                    pedido=pedido,
                    fecha_uso=fecha_ped,
                )

            secuencia = ['pendiente']
            if estado in ('pagado', 'confirmado', 'en_camino', 'entregado'):
                secuencia.append('pagado')
            if estado in ('confirmado', 'en_camino', 'entregado'):
                secuencia.append('confirmado')
            if estado in ('en_camino', 'entregado'):
                secuencia.append('en_camino')
            if estado == 'entregado':
                secuencia.append('entregado')
            if estado == 'cancelado':
                secuencia.append('cancelado')

            for step_idx, est in enumerate(secuencia):
                HistorialEstadoPedido.objects.create(
                    tienda=tienda,
                    pedido=pedido,
                    estado=est,
                    fecha=fecha_ped + timedelta(hours=step_idx * 6),
                    observacion=f'Transición registrada a {est}',
                )

            metodo = rng.choice(metodos_pago)
            estado_pago = 'completado' if estado in ('pagado', 'confirmado', 'en_camino', 'entregado') else ('fallido' if estado == 'cancelado' else 'pendiente')
            Pago.objects.create(
                tienda=tienda,
                pedido=pedido,
                metodo_pago=metodo,
                monto=total,
                estado=estado_pago,
                fecha=fecha_ped + timedelta(minutes=12),
                referencia_transaccion=f'TXN-KM-{pedido.id:05d}',
            )

            dir_envio = direcciones[(tienda.id, cliente.id)]
            if estado in ('en_camino', 'entregado'):
                Envio.objects.create(
                    tienda=tienda,
                    pedido=pedido,
                    direccion_envio=dir_envio,
                    transportista=rng.choice(['Kantu Express', 'DHL Bolivia', 'Urbano']),
                    numero_seguimiento=f'TRK-{tienda.id}{pedido.id:05d}',
                    fecha_envio=fecha_ped + timedelta(days=1),
                    fecha_entrega=(fecha_ped + timedelta(days=3)) if estado == 'entregado' else None,
                )

            if estado == 'entregado' and rng.random() < 0.45:
                nota, texto = rng.choice(comentarios_ok if rng.random() < 0.85 else comentarios_mix)
                Resena.objects.create(
                    tienda=tienda,
                    cliente=cliente,
                    producto=items_data[0][0].producto,
                    calificacion=nota,
                    comentario=texto,
                    fecha=fecha_ped + timedelta(days=4),
                )
            pedidos.append(pedido)
        return pedidos

    def _sembrar_finanzas_mensuales(self, tiendas: list, admin: Usuario, hoy: date):
        categorias_gasto = [
            ('Alquiler', 'Alquiler mensual de showroom y almacén', Decimal('2400.00')),
            ('Sueldos', 'Planilla operativa y atención al cliente', Decimal('4800.00')),
            ('Servicios', 'Energía eléctrica, fibra óptica y logística', Decimal('650.00')),
            ('Marketing', 'Pauta digital en redes sociales', Decimal('900.00')),
        ]
        for mes_offset in range(10):
            # Primer día del mes correspondiente
            anio = hoy.year
            mes = hoy.month - mes_offset
            while mes <= 0:
                mes += 12
                anio -= 1
            fecha_mes = date(anio, mes, 5)
            fin_mes = (date(anio, mes, 28))

            for tienda in tiendas:
                for cat, desc, base in categorias_gasto:
                    GastoOperativo.objects.get_or_create(
                        tienda=tienda,
                        categoria=cat,
                        fecha=fecha_mes,
                        defaults={
                            'descripcion': f'{desc} ({anio}-{mes:02d})',
                            'monto': base if tienda.id == tiendas[0].id else _q2(base * Decimal('0.65')),
                        },
                    )

                if mes_offset >= 1:
                    ventas_mes = Decimal('0.00')
                    pedidos_mes = Pedido.objects.filter(
                        tienda=tienda,
                        fecha__year=anio,
                        fecha__month=mes,
                        estado_actual__in=('pagado', 'confirmado', 'en_camino', 'entregado'),
                    )
                    for p in pedidos_mes:
                        ventas_mes += p.total
                    if ventas_mes > Decimal('0.00'):
                        comision_pct = Decimal('5.00') if tienda.propietario.email == 'empresa1@kantu.bo' else Decimal('8.00')
                        monto_com = _q2(ventas_mes * comision_pct / Decimal('100.00'))
                        neto = _q2(ventas_mes - monto_com)
                        estado_liq = (
                            LiquidacionTienda.Estado.PAGADA
                            if mes_offset >= 3
                            else (LiquidacionTienda.Estado.APROBADA if mes_offset == 2 else LiquidacionTienda.Estado.PENDIENTE)
                        )
                        LiquidacionTienda.objects.get_or_create(
                            tienda=tienda,
                            periodo_inicio=date(anio, mes, 1),
                            periodo_fin=fin_mes,
                            defaults={
                                'cantidad_pedidos': pedidos_mes.count(),
                                'total_ventas': ventas_mes,
                                'comision_porcentaje': comision_pct,
                                'monto_comision': monto_com,
                                'monto_neto': neto,
                                'estado': estado_liq,
                                'referencia_pago': f'BCP-LIQ-{tienda.id}-{anio}{mes:02d}' if estado_liq == LiquidacionTienda.Estado.PAGADA else '',
                                'pagado_en': timezone.now() if estado_liq == LiquidacionTienda.Estado.PAGADA else None,
                                'generado_por': admin,
                                'notas': f'Liquidación mensual {anio}-{mes:02d}',
                            },
                        )

    def _sembrar_crm_tickets_carritos(
        self,
        *,
        rng: random.Random,
        tiendas: list,
        clientes: list,
        catalogo: list,
        pedidos: list,
        ahora: datetime,
    ):
        for tienda in tiendas:
            ReglaSegmentacion.objects.get_or_create(
                tienda=tienda,
                defaults={'dias_inactividad': 60, 'min_compras_frecuente': 3, 'umbral_alto_valor': Decimal('800.00')},
            )
            seg_vip, _ = Segmento.objects.get_or_create(
                tienda=tienda, nombre='Clientes VIP', defaults={'criterio': 'Compras >= Bs 800'}
            )
            for cliente in clientes[:6]:
                ficha, _ = FichaCliente.objects.get_or_create(
                    cliente=cliente, tienda=tienda, defaults={'segmento': seg_vip}
                )
                InteraccionCliente.objects.get_or_create(
                    tienda=tienda,
                    ficha_cliente=ficha,
                    tipo='consulta_preventa',
                    defaults={
                        'mensaje': 'Consulta sobre disponibilidad de tallas y despacho a domicilio.',
                        'estado': 'resuelto',
                        'fecha': self._fecha_organica(rng, ahora),
                    },
                )
                wl, _ = ListaDeseos.objects.get_or_create(
                    tienda=tienda,
                    ficha_cliente=ficha,
                    defaults={'fecha_creacion': self._fecha_organica(rng, ahora)},
                )
                prods_t = [v.producto for v in catalogo if v.producto.tienda_id == tienda.id]
                if prods_t:
                    ItemListaDeseos.objects.get_or_create(tienda=tienda, lista_deseos=wl, producto=prods_t[0])

            recalcular_segmentos_tienda(tienda)

            camp_cart, _ = CampanaCarrito.objects.get_or_create(
                tienda=tienda,
                defaults={
                    'activo': True,
                    'horas_inactividad': 2,
                    'descuento_porcentaje': 10,
                    'codigo_cupon': 'RECUPERA10',
                },
            )
            vars_t = [v for v in catalogo if v.producto.tienda_id == tienda.id]
            for idx_c, cliente in enumerate(clientes[:4]):
                carrito, _ = Carrito.objects.get_or_create(
                    cliente=cliente,
                    tienda=tienda,
                    defaults={
                        'fecha_creacion': ahora - timedelta(hours=6 + idx_c * 3),
                        'ultima_actividad': ahora - timedelta(hours=5 + idx_c * 3),
                    },
                )
                if vars_t:
                    ItemCarrito.objects.get_or_create(
                        tienda=tienda,
                        carrito=carrito,
                        variante=vars_t[0],
                        defaults={'cantidad': 1},
                    )
                RegistroRecuperacionCarrito.objects.get_or_create(
                    campana=camp_cart,
                    carrito=carrito,
                    cliente=cliente,
                    defaults={
                        'recuperado': idx_c == 0,
                        'correo_enviado': True,
                        'fecha_envio': ahora - timedelta(hours=2),
                    },
                )

        # Tickets de soporte en todos los estados
        estados_tck = ['abierto', 'en_proceso', 'resuelto', 'cerrado']
        asuntos = [
            ('consulta', 'Consulta sobre guía de tallas', '¿Las prendas de alpaca ceden tras el primer lavado?'),
            ('demora_envio', 'Seguimiento de envío pendiente', 'Mi pedido figura en camino hace 48 horas, ¿podrían confirmar el tracking?'),
            ('reclamo_producto', 'Cambio de talla solicitado', 'Necesito cambiar la chompa de talla M a L manteniendo el color.'),
            ('devolucion', 'Solicitud de nota de crédito', 'El artículo no coincide con lo esperado y deseo gestionar devolución.'),
        ]
        for idx, pedido in enumerate(pedidos[:12]):
            tipo, asunto, desc = asuntos[idx % len(asuntos)]
            estado_tck = estados_tck[idx % len(estados_tck)]
            tck = TicketSoporte.objects.create(
                cliente=pedido.cliente,
                tienda=pedido.tienda,
                pedido=pedido,
                tipo=tipo,
                prioridad=rng.choice(['baja', 'media', 'alta']),
                estado=estado_tck,
                asunto=asunto,
                descripcion=desc,
                fecha_creacion=pedido.fecha + timedelta(days=2),
                fecha_actualizacion=pedido.fecha + timedelta(days=3),
            )
            MensajeTicket.objects.create(
                ticket=tck,
                autor=pedido.cliente,
                contenido=desc,
                fecha_envio=pedido.fecha + timedelta(days=2),
            )
            if estado_tck != 'abierto':
                MensajeTicket.objects.create(
                    ticket=tck,
                    autor=pedido.tienda.propietario,
                    contenido='¡Hola! Ya revisamos tu solicitud y estamos coordinando la solución.',
                    fecha_envio=pedido.fecha + timedelta(days=2, hours=4),
                )

    def _sembrar_ia_y_auditoria(
        self,
        *,
        rng: random.Random,
        total_eventos: int,
        tiendas: list,
        clientes: list,
        catalogo: list,
        usuarios: dict,
        ahora: datetime,
    ):
        productos = list({v.producto for v in catalogo})
        tipos_evt = [
            EventoUsuario.TipoEvento.VIEW,
            EventoUsuario.TipoEvento.CLICK,
            EventoUsuario.TipoEvento.SEARCH,
            EventoUsuario.TipoEvento.CART,
        ]
        busquedas = ['alpaca', 'poncho', 'chaqueta', 'chompa', 'manta', 'bufanda']
        for _ in range(total_eventos):
            prod = rng.choice(productos)
            tipo = rng.choices(tipos_evt, weights=[50, 25, 15, 10], k=1)[0]
            EventoUsuario.objects.create(
                cliente=rng.choice(clientes),
                tienda=prod.tienda,
                producto=None if tipo == EventoUsuario.TipoEvento.SEARCH else prod,
                tipo_evento=tipo,
                termino_busqueda=rng.choice(busquedas) if tipo == EventoUsuario.TipoEvento.SEARCH else '',
                fecha=self._fecha_organica(rng, ahora),
                metadata={'origen': 'seed_10_months'},
            )

        for cliente in clientes[:5]:
            for prod in rng.sample(productos, k=min(3, len(productos))):
                Recomendacion.objects.create(
                    tienda=prod.tienda,
                    cliente=cliente,
                    producto=prod,
                    score=Decimal(str(round(rng.uniform(0.72, 0.98), 4))),
                    fecha_generada=ahora - timedelta(days=rng.randint(1, 15)),
                )

        ReporteGenerado.objects.create(
            tienda=tiendas[0],
            generado_por_usuario=tiendas[0].propietario,
            tipo_reporte='informe_ia',
            formato='json',
            titulo='Resumen comercial últimos 10 meses',
            pregunta='¿Cuál fue la evolución mensual de ventas en los últimos 10 meses?',
            analisis='Se observa crecimiento sostenido con mayor concentración en los últimos 3 meses.',
            fecha_generacion=ahora - timedelta(days=2),
        )

        # Bitácora de accesos (exitosos y fallidos) y auditoría administrativa
        for usr in [usuarios['admin'], *usuarios['empresas'], *usuarios['clientes'][:4]]:
            BitacoraAcceso.objects.create(
                usuario=usr,
                email_intento=usr.email,
                ip='127.0.0.1',
                exitoso=True,
                dispositivo='Chrome/158.0 Windows',
                fecha=self._fecha_organica(rng, ahora),
            )
        BitacoraAcceso.objects.create(
            usuario=None,
            email_intento='intruso@desconocido.bo',
            ip='190.181.20.14',
            exitoso=False,
            motivo='Credenciales inválidas',
            dispositivo='Mozilla/5.0',
            fecha=ahora - timedelta(days=3),
        )
        LogAuditoria.objects.create(
            usuario=usuarios['admin'],
            tabla_afectada='plan_suscripcion',
            registro_id=1,
            accion='CREAR',
            datos_nuevos={'codigo': 'estandar', 'max_tiendas': 3},
            fecha=ahora - timedelta(days=15),
        )

    def _imprimir_credenciales(self):
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('=== CREDENCIALES DE PRUEBA (Password para todos: Kantu2026!) ==='))
        self.stdout.write('  Administrador : admin@kantu.bo')
        self.stdout.write('  Empresa 1     : empresa1@kantu.bo  (Alto volumen, 2 tiendas, Plan Premium)')
        self.stdout.write('  Empresa 2     : empresa2@kantu.bo  (Volumen moderado, 1 tienda, Plan Estándar)')
        self.stdout.write('  Empresa 3     : empresa3@kantu.bo  (Nueva, 1 tienda, Plan Estándar en prueba)')
        self.stdout.write('  Cliente 1     : cliente1@kantu.bo  (Recurrente / Alto Valor)')
        self.stdout.write('  Cliente 2     : cliente2@kantu.bo  (Frecuente)')
        self.stdout.write('  Cliente 3     : cliente3@kantu.bo  (Esporádico)')
