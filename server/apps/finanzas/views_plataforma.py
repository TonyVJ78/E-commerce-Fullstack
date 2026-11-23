"""Controladores REST API administrativos para Planes de Suscripción y Liquidación de Tiendas (CU-37)."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import stripe
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tiendas.models import Tienda
from apps.usuarios.audit import ACCION_ACTUALIZAR, ACCION_CREAR, registrar_auditoria, snapshot_instancia

from .tipo_cambio import tipo_cambio_vigente

from .liquidaciones import (
    ErrorLiquidacion,
    asignar_suscripcion_a_tienda,
    calcular_totales_periodo,
    generar_liquidacion_tienda,
    suscripcion_vigente_de_tienda,
    transicionar_liquidacion,
)
from .models import LiquidacionTienda, PlanSuscripcion, SuscripcionTienda
from .serializers import (
    AsignarSuscripcionSerializer,
    GenerarLiquidacionSerializer,
    LiquidacionTiendaSerializer,
    PagarLiquidacionSerializer,
    PlanSuscripcionSerializer,
    SuscripcionTiendaSerializer,
)


class IsAdminPlataforma(permissions.BasePermission):
    """Restringe acceso exclusivamente a administradores de plataforma o superusuarios."""

    message = 'Acceso restringido a administradores de plataforma.'

    def has_permission(self, request, view) -> bool:
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        rol = getattr(user, 'rol', None)
        return bool(rol and getattr(rol, 'nombre', '').strip().lower() == 'administrador')


class PlanSuscripcionListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/finanzas/plataforma/planes/"""

    permission_classes = [IsAdminPlataforma]
    serializer_class = PlanSuscripcionSerializer
    queryset = PlanSuscripcion.objects.all()

    def perform_create(self, serializer):
        plan = serializer.save()
        registrar_auditoria(
            self.request,
            ACCION_CREAR,
            tabla='plan_suscripcion',
            registro_id=plan.id,
            datos_nuevos=snapshot_instancia(plan),
        )


class PlanSuscripcionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/finanzas/plataforma/planes/<pk>/"""

    permission_classes = [IsAdminPlataforma]
    serializer_class = PlanSuscripcionSerializer
    queryset = PlanSuscripcion.objects.all()

    def perform_update(self, serializer):
        anterior = snapshot_instancia(serializer.instance)
        plan = serializer.save()
        registrar_auditoria(
            self.request,
            ACCION_ACTUALIZAR,
            tabla='plan_suscripcion',
            registro_id=plan.id,
            datos_anteriores=anterior,
            datos_nuevos=snapshot_instancia(plan),
        )

    def destroy(self, request, *args, **kwargs):
        plan = self.get_object()
        if SuscripcionTienda.objects.filter(
            plan=plan,
            estado__in=(SuscripcionTienda.Estado.ACTIVA, SuscripcionTienda.Estado.PRUEBA),
        ).exists():
            return Response(
                {'error': 'No se puede desactivar o eliminar un plan con tiendas suscritas vigentes.'},
                status=status.HTTP_409_CONFLICT,
            )
        anterior = snapshot_instancia(plan)
        plan.activo = False
        plan.save(update_fields=['activo'])
        registrar_auditoria(
            request,
            ACCION_ACTUALIZAR,
            tabla='plan_suscripcion',
            registro_id=plan.id,
            datos_anteriores=anterior,
            datos_nuevos=snapshot_instancia(plan),
        )
        return Response(PlanSuscripcionSerializer(plan).data)


class SuscripcionesResumenView(APIView):
    """GET /api/finanzas/plataforma/suscripciones/ — lista todas las tiendas con su suscripción vigente."""

    permission_classes = [IsAdminPlataforma]

    def get(self, request):
        tiendas = Tienda.objects.select_related('propietario').order_by('nombre', 'id')
        filas = []
        for tienda in tiendas:
            vigente = suscripcion_vigente_de_tienda(tienda)
            ultima = vigente or SuscripcionTienda.objects.select_related('plan').filter(tienda=tienda).first()
            filas.append({
                'tienda_id': tienda.id,
                'tienda_nombre': tienda.nombre,
                'tienda_slug': tienda.slug,
                'tienda_activa': tienda.activa,
                'propietario_email': getattr(tienda.propietario, 'email', ''),
                'suscripcion': SuscripcionTiendaSerializer(ultima).data if ultima else None,
            })
        return Response({'tiendas': filas})


class AsignarSuscripcionTiendaView(APIView):
    """POST /api/finanzas/plataforma/tiendas/<tienda_id>/suscripcion/"""

    permission_classes = [IsAdminPlataforma]

    def post(self, request, tienda_id: int):
        tienda = get_object_or_404(Tienda, pk=tienda_id)
        serializer = AsignarSuscripcionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        try:
            suscripcion = asignar_suscripcion_a_tienda(
                tienda=tienda,
                plan=datos['plan'],
                estado=datos['estado'],
                fecha_inicio=datos['fecha_inicio'],
                fecha_fin=datos['fecha_fin'],
                auto_renovar=datos['auto_renovar'],
                usuario=request.user,
            )
        except ErrorLiquidacion as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SuscripcionTiendaSerializer(suscripcion).data, status=status.HTTP_201_CREATED)


class LiquidacionPrevisualizarView(APIView):
    """POST /api/finanzas/plataforma/liquidaciones/previsualizar/"""

    permission_classes = [IsAdminPlataforma]

    def post(self, request):
        serializer = GenerarLiquidacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        try:
            resumen = calcular_totales_periodo(
                datos['tienda'],
                datos['periodo_inicio'],
                datos['periodo_fin'],
            )
        except ErrorLiquidacion as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            **resumen,
            'total_ventas': str(resumen['total_ventas']),
            'comision_porcentaje': str(resumen['comision_porcentaje']),
            'monto_comision': str(resumen['monto_comision']),
            'monto_neto': str(resumen['monto_neto']),
        })


class LiquidacionListCreateView(APIView):
    """GET/POST /api/finanzas/plataforma/liquidaciones/"""

    permission_classes = [IsAdminPlataforma]

    def get(self, request):
        qs = LiquidacionTienda.objects.select_related('tienda', 'generado_por').all()
        tienda_id = request.query_params.get('tienda')
        estado = request.query_params.get('estado')
        if tienda_id:
            qs = qs.filter(tienda_id=tienda_id)
        if estado:
            qs = qs.filter(estado=estado)
        return Response(LiquidacionTiendaSerializer(qs, many=True).data)

    def post(self, request):
        serializer = GenerarLiquidacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        try:
            liquidacion = generar_liquidacion_tienda(
                tienda=datos['tienda'],
                periodo_inicio=datos['periodo_inicio'],
                periodo_fin=datos['periodo_fin'],
                usuario=request.user,
                notas=datos.get('notas', ''),
            )
        except ErrorLiquidacion as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LiquidacionTiendaSerializer(liquidacion).data, status=status.HTTP_201_CREATED)


class LiquidacionAccionView(APIView):
    """POST /api/finanzas/plataforma/liquidaciones/<pk>/<accion>/ (aprobar, pagar, anular)"""

    permission_classes = [IsAdminPlataforma]

    def post(self, request, pk: int, accion: str):
        liquidacion = get_object_or_404(LiquidacionTienda, pk=pk)
        serializer = PagarLiquidacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        try:
            actualizada = transicionar_liquidacion(
                liquidacion=liquidacion,
                accion=accion,
                usuario=request.user,
                referencia_pago=datos.get('referencia_pago', ''),
                notas=datos.get('notas', ''),
            )
        except ErrorLiquidacion as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LiquidacionTiendaSerializer(actualizada).data)


def _obtener_plan_y_tiendas(user, plan_id):
    """Obtiene un plan activo y valida que el usuario tenga entre 1 y `max_tiendas` tiendas."""
    plan = get_object_or_404(PlanSuscripcion, pk=plan_id, activo=True)
    tiendas = list(Tienda.objects.filter(propietario=user).order_by('id'))
    if not tiendas:
        return None, None, Response(
            {'error': 'Primero debes registrar al menos una tienda para activar un plan.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(tiendas) > plan.max_tiendas:
        return None, None, Response(
            {
                'error': (
                    f'Tu cuenta tiene {len(tiendas)} tienda(s) y el {plan.nombre} '
                    f'permite hasta {plan.max_tiendas}.'
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return plan, tiendas, None


def _verificar_pago_stripe_plan(user, plan, payment_intent_id: str):
    """Valida en Stripe que el PaymentIntent esté pagado y pertenezca al usuario y plan."""
    if not payment_intent_id:
        return Response(
            {'error': 'Debe completar el pago con tarjeta en Stripe antes de activar este plan.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not settings.STRIPE_SECRET_KEY:
        return Response(
            {'error': 'La pasarela de pagos Stripe no está configurada en el servidor.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except stripe.error.StripeError as exc:
        return Response(
            {'error': f'No se pudo verificar el pago en Stripe: {exc.user_message or str(exc)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if getattr(intent, 'status', None) != 'succeeded':
        return Response(
            {'error': f'El pago aún no se completó (estado: {getattr(intent, "status", "desconocido")}).'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    metadata = getattr(intent, 'metadata', {}) or {}
    if hasattr(metadata, 'to_dict'):
        metadata = metadata.to_dict()
    if (
        metadata.get('tipo') != 'suscripcion_plan'
        or str(metadata.get('usuario_id', '')) != str(user.id)
        or str(metadata.get('plan_id', '')) != str(plan.id)
    ):
        return Response(
            {'error': 'El comprobante de pago no corresponde a este usuario o plan.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


class MiSuscripcionEmpresaView(APIView):
    """GET/POST /api/finanzas/mi-suscripcion/ para propietarios de tiendas (rol empresa)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        planes = PlanSuscripcion.objects.filter(activo=True).order_by('precio_mensual', 'id')
        tiendas = list(Tienda.objects.filter(propietario=request.user).order_by('id'))
        filas_tiendas = []
        suscripcion_actual = None
        for tienda in tiendas:
            susc = suscripcion_vigente_de_tienda(tienda)
            if susc and suscripcion_actual is None:
                suscripcion_actual = susc
            filas_tiendas.append({
                'tienda_id': tienda.id,
                'tienda_nombre': tienda.nombre,
                'tienda_activa': tienda.activa,
                'suscripcion': SuscripcionTiendaSerializer(susc).data if susc else None,
            })
        return Response({
            'planes': PlanSuscripcionSerializer(planes, many=True).data,
            'tiendas_actuales': len(tiendas),
            'tiendas': filas_tiendas,
            'suscripcion_actual': (
                SuscripcionTiendaSerializer(suscripcion_actual).data if suscripcion_actual else None
            ),
        })

    def post(self, request):
        plan, tiendas, error_resp = _obtener_plan_y_tiendas(request.user, request.data.get('plan_id'))
        if error_resp is not None:
            return error_resp

        if plan.precio_mensual > Decimal('0.00'):
            payment_intent_id = (request.data.get('payment_intent_id') or '').strip()
            error_pago = _verificar_pago_stripe_plan(request.user, plan, payment_intent_id)
            if error_pago is not None:
                return error_pago

        hoy = date.today()
        fin = hoy + timedelta(days=30)
        ultima = None
        for tienda in tiendas:
            ultima = asignar_suscripcion_a_tienda(
                tienda=tienda,
                plan=plan,
                estado=SuscripcionTienda.Estado.ACTIVA,
                fecha_inicio=hoy,
                fecha_fin=fin,
                auto_renovar=True,
                usuario=request.user,
            )
        return Response(
            SuscripcionTiendaSerializer(ultima).data,
            status=status.HTTP_201_CREATED,
        )


class MiSuscripcionIntentoPagoView(APIView):
    """POST /api/finanzas/mi-suscripcion/pago-intento/ — Crea PaymentIntent Stripe para el plan."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        plan, _, error_resp = _obtener_plan_y_tiendas(request.user, request.data.get('plan_id'))
        if error_resp is not None:
            return error_resp

        if plan.precio_mensual <= Decimal('0.00'):
            return Response({'requiere_pago': False, 'plan': PlanSuscripcionSerializer(plan).data})

        if not settings.STRIPE_SECRET_KEY:
            return Response(
                {'error': 'La pasarela de pagos Stripe no está configurada en el servidor.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        cotizacion = tipo_cambio_vigente()
        if not cotizacion or not cotizacion.usd_bob or cotizacion.usd_bob <= 0:
            return Response(
                {'error': 'No hay tipo de cambio USD vigente cargado para procesar el pago.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tasa = Decimal(str(cotizacion.usd_bob))
        monto_usd = (plan.precio_mensual / tasa).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        centavos = max(int(monto_usd * 100), 50)

        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            intent = stripe.PaymentIntent.create(
                amount=centavos,
                currency='usd',
                automatic_payment_methods={'enabled': True, 'allow_redirects': 'never'},
                metadata={
                    'tipo': 'suscripcion_plan',
                    'usuario_id': str(request.user.id),
                    'usuario_email': request.user.email,
                    'plan_id': str(plan.id),
                    'plan_codigo': plan.codigo,
                    'monto_bs': str(plan.precio_mensual),
                    'tipo_cambio_usd': str(tasa),
                },
            )
        except stripe.error.StripeError as exc:
            return Response(
                {'error': f'No se pudo iniciar el pago con Stripe: {exc.user_message or str(exc)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'requiere_pago': True,
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id,
                'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
                'monto_bs': str(plan.precio_mensual),
                'monto_usd': str(monto_usd),
                'tipo_cambio_usd': str(tasa),
                'plan': PlanSuscripcionSerializer(plan).data,
            },
            status=status.HTTP_200_OK,
        )
