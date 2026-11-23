"""Pruebas unitarias y de API para CU-37: Planes de suscripción y liquidación de tiendas."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.finanzas.models import LiquidacionTienda, PlanSuscripcion, SuscripcionTienda, TipoCambio
from apps.pedidos.models import Pedido
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol

Usuario = get_user_model()


class Cu37SuscripcionesYLiquidacionesTests(TestCase):
    def setUp(self):
        self.rol_admin, _ = Rol.objects.get_or_create(nombre='administrador')
        self.rol_empresa, _ = Rol.objects.get_or_create(nombre='empresa')

        self.admin = Usuario.objects.create_user(
            email='admin_cu37@kantumarket.test',
            password='Password123!',
            first_name='Admin',
            last_name='Plataforma',
            rol=self.rol_admin,
        )
        self.dueno = Usuario.objects.create_user(
            email='tienda_cu37@kantumarket.test',
            password='Password123!',
            first_name='Dueño',
            last_name='Tienda',
            rol=self.rol_empresa,
        )
        self.tienda = Tienda.objects.create(
            propietario=self.dueno,
            nombre='Boutique Kantu',
            slug='boutique-kantu-cu37',
        )

        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)

        self.client_empresa = APIClient()
        self.client_empresa.force_authenticate(user=self.dueno)

    def test_solo_administrador_accede_a_planes_y_liquidaciones(self):
        resp = self.client_empresa.get('/api/finanzas/plataforma/planes/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp_liq = self.client_empresa.get('/api/finanzas/plataforma/liquidaciones/')
        self.assertEqual(resp_liq.status_code, status.HTTP_403_FORBIDDEN)

    def test_crud_plan_asignacion_y_bloqueo_desactivar_en_uso(self):
        crear = self.client_admin.post(
            '/api/finanzas/plataforma/planes/',
            {
                'codigo': 'pro-10',
                'nombre': 'Plan Pro',
                'descripcion': 'Plan profesional',
                'precio_mensual': '250.00',
                'comision_porcentaje': '10.00',
                'max_productos': 500,
                'max_usuarios': 10,
            },
            format='json',
        )
        self.assertEqual(crear.status_code, status.HTTP_201_CREATED)
        plan_id = crear.data['id']

        hoy = date.today()
        asignar = self.client_admin.post(
            f'/api/finanzas/plataforma/tiendas/{self.tienda.id}/suscripcion/',
            {
                'plan': plan_id,
                'estado': 'activa',
                'fecha_inicio': str(hoy),
                'fecha_fin': str(hoy + timedelta(days=30)),
                'auto_renovar': True,
            },
            format='json',
        )
        self.assertEqual(asignar.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SuscripcionTienda.objects.filter(tienda=self.tienda, plan_id=plan_id).count(), 1)

        # No permite desactivar un plan con suscripción activa
        baja = self.client_admin.delete(f'/api/finanzas/plataforma/planes/{plan_id}/')
        self.assertEqual(baja.status_code, status.HTTP_409_CONFLICT)

    def test_flujo_completo_liquidacion_con_comision_del_plan(self):
        plan = PlanSuscripcion.objects.create(
            codigo='oro-8',
            nombre='Plan Oro',
            precio_mensual=Decimal('300.00'),
            comision_porcentaje=Decimal('8.00'),
        )
        hoy = date.today()
        SuscripcionTienda.objects.create(
            tienda=self.tienda,
            plan=plan,
            estado=SuscripcionTienda.Estado.ACTIVA,
            fecha_inicio=hoy - timedelta(days=10),
            fecha_fin=hoy + timedelta(days=20),
        )

        # Pedidos liquidables vs no liquidables
        Pedido.objects.create(
            cliente=self.dueno,
            tienda=self.tienda,
            estado_actual='pagado',
            subtotal=Decimal('1000.00'),
            total=Decimal('1000.00'),
        )
        Pedido.objects.create(
            cliente=self.dueno,
            tienda=self.tienda,
            estado_actual='cancelado',
            subtotal=Decimal('500.00'),
            total=Decimal('500.00'),
        )

        payload = {
            'tienda': self.tienda.id,
            'periodo_inicio': str(hoy - timedelta(days=1)),
            'periodo_fin': str(hoy + timedelta(days=1)),
        }
        prev = self.client_admin.post(
            '/api/finanzas/plataforma/liquidaciones/previsualizar/',
            payload,
            format='json',
        )
        self.assertEqual(prev.status_code, status.HTTP_200_OK)
        self.assertEqual(prev.data['cantidad_pedidos'], 1)
        self.assertEqual(prev.data['total_ventas'], '1000.00')
        self.assertEqual(prev.data['monto_comision'], '80.00')
        self.assertEqual(prev.data['monto_neto'], '920.00')

        gen = self.client_admin.post('/api/finanzas/plataforma/liquidaciones/', payload, format='json')
        self.assertEqual(gen.status_code, status.HTTP_201_CREATED)
        liq_id = gen.data['id']

        # Prevenir doble liquidación del mismo periodo
        dup = self.client_admin.post('/api/finanzas/plataforma/liquidaciones/', payload, format='json')
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)

        # Aprobar y pagar con referencia
        aprobar = self.client_admin.post(f'/api/finanzas/plataforma/liquidaciones/{liq_id}/aprobar/', {}, format='json')
        self.assertEqual(aprobar.status_code, status.HTTP_200_OK)
        self.assertEqual(aprobar.data['estado'], 'aprobada')

        pagar = self.client_admin.post(
            f'/api/finanzas/plataforma/liquidaciones/{liq_id}/pagar/',
            {'referencia_pago': 'TRF-2026-0091'},
            format='json',
        )
        self.assertEqual(pagar.status_code, status.HTTP_200_OK)
        self.assertEqual(pagar.data['estado'], 'pagada')
        self.assertEqual(pagar.data['referencia_pago'], 'TRF-2026-0091')

        # No se puede anular una liquidación ya pagada
        anular = self.client_admin.post(f'/api/finanzas/plataforma/liquidaciones/{liq_id}/anular/', {}, format='json')
        self.assertEqual(anular.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(LiquidacionTienda.objects.get(pk=liq_id).estado, LiquidacionTienda.Estado.PAGADA)

    @override_settings(STRIPE_SECRET_KEY='sk_test_cu37', STRIPE_PUBLISHABLE_KEY='pk_test_cu37')
    def test_empresa_consulta_y_elige_plan_estandar_o_premium_con_stripe(self):
        TipoCambio.objects.create(fecha=date.today(), usd_bob=Decimal('10.0000'), fuente='TEST')
        resp = self.client_empresa.get('/api/finanzas/mi-suscripcion/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codigos = {p['codigo']: p['max_tiendas'] for p in resp.data['planes']}
        self.assertEqual(codigos.get('estandar'), 3)
        self.assertEqual(codigos.get('premium'), 10)

        plan_premium = PlanSuscripcion.objects.get(codigo='premium')

        # Sin payment_intent_id debe rechazar la activación de un plan pago
        sin_pago = self.client_empresa.post(
            '/api/finanzas/mi-suscripcion/',
            {'plan_id': plan_premium.id},
            format='json',
        )
        self.assertEqual(sin_pago.status_code, status.HTTP_400_BAD_REQUEST)

        with mock.patch(
            'stripe.PaymentIntent.create',
            return_value=SimpleNamespace(id='pi_cu37_plan', client_secret='cs_cu37_plan'),
        ):
            intento = self.client_empresa.post(
                '/api/finanzas/mi-suscripcion/pago-intento/',
                {'plan_id': plan_premium.id},
                format='json',
            )
        self.assertEqual(intento.status_code, status.HTTP_200_OK)
        self.assertTrue(intento.data['requiere_pago'])
        self.assertEqual(intento.data['client_secret'], 'cs_cu37_plan')

        intento_ok = stripe.PaymentIntent.construct_from(
            {
                'id': 'pi_cu37_plan',
                'status': 'succeeded',
                'currency': 'usd',
                'metadata': {
                    'tipo': 'suscripcion_plan',
                    'usuario_id': str(self.dueno.id),
                    'plan_id': str(plan_premium.id),
                },
            },
            'sk_test_cu37',
        )
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=intento_ok):
            activar = self.client_empresa.post(
                '/api/finanzas/mi-suscripcion/',
                {'plan_id': plan_premium.id, 'payment_intent_id': 'pi_cu37_plan'},
                format='json',
            )
        self.assertEqual(activar.status_code, status.HTTP_201_CREATED)
        self.assertEqual(activar.data['max_tiendas'], 10)
