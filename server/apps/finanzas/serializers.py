from decimal import Decimal

from rest_framework import serializers

from apps.tiendas.models import Tienda

from .models import (
    GastoOperativo,
    LiquidacionTienda,
    PlanSuscripcion,
    SuscripcionTienda,
    TipoCambio,
)


class TipoCambioSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoCambio
        fields = ['fecha', 'usd_bob', 'ufv_bob', 'fuente']


class GastoOperativoSerializer(serializers.ModelSerializer):
    categoria_etiqueta = serializers.CharField(source='get_categoria_display', read_only=True)
    monto = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))

    class Meta:
        model = GastoOperativo
        fields = [
            'id', 'tienda', 'categoria', 'categoria_etiqueta', 'descripcion',
            'monto', 'fecha', 'registrado_por', 'creado',
        ]
        read_only_fields = ['tienda', 'registrado_por', 'creado']


class GastoFiltroSerializer(serializers.Serializer):
    """Filtros de la lista y de los totales: se validan igual que un cuerpo de petición."""
    desde = serializers.DateField(required=False)
    hasta = serializers.DateField(required=False)
    categoria = serializers.ChoiceField(choices=GastoOperativo.Categoria.choices, required=False)

    def validate(self, attrs):
        if 'desde' in attrs and 'hasta' in attrs and attrs['desde'] > attrs['hasta']:
            raise serializers.ValidationError({'desde': 'La fecha inicial es posterior a la final.'})
        return attrs


class PlanSuscripcionSerializer(serializers.ModelSerializer):
    precio_mensual = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.00'))
    comision_porcentaje = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0.00'),
        max_value=Decimal('100.00'),
    )

    class Meta:
        model = PlanSuscripcion
        fields = [
            'id', 'codigo', 'nombre', 'descripcion', 'precio_mensual',
            'comision_porcentaje', 'max_tiendas', 'max_productos', 'max_usuarios', 'activo', 'creado',
        ]
        read_only_fields = ['creado']


class SuscripcionTiendaSerializer(serializers.ModelSerializer):
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    plan_nombre = serializers.CharField(source='plan.nombre', read_only=True)
    max_tiendas = serializers.IntegerField(source='plan.max_tiendas', read_only=True)
    comision_porcentaje = serializers.DecimalField(
        source='plan.comision_porcentaje', max_digits=5, decimal_places=2, read_only=True
    )
    precio_mensual = serializers.DecimalField(
        source='plan.precio_mensual', max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = SuscripcionTienda
        fields = [
            'id', 'tienda', 'tienda_nombre', 'plan', 'plan_nombre',
            'max_tiendas', 'precio_mensual', 'comision_porcentaje', 'estado',
            'fecha_inicio', 'fecha_fin', 'auto_renovar', 'actualizado',
        ]
        read_only_fields = ['actualizado']


class AsignarSuscripcionSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=PlanSuscripcion.objects.all())
    estado = serializers.ChoiceField(
        choices=SuscripcionTienda.Estado.choices,
        default=SuscripcionTienda.Estado.ACTIVA,
    )
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()
    auto_renovar = serializers.BooleanField(default=True)


class LiquidacionTiendaSerializer(serializers.ModelSerializer):
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    generado_por_email = serializers.CharField(source='generado_por.email', read_only=True, default='')

    class Meta:
        model = LiquidacionTienda
        fields = [
            'id', 'tienda', 'tienda_nombre', 'periodo_inicio', 'periodo_fin',
            'cantidad_pedidos', 'total_ventas', 'comision_porcentaje',
            'monto_comision', 'monto_neto', 'estado', 'referencia_pago',
            'notas', 'generado_por', 'generado_por_email', 'creado', 'pagado_en',
        ]
        read_only_fields = fields


class GenerarLiquidacionSerializer(serializers.Serializer):
    tienda = serializers.PrimaryKeyRelatedField(queryset=Tienda.objects.all())
    periodo_inicio = serializers.DateField()
    periodo_fin = serializers.DateField()
    notas = serializers.CharField(required=False, allow_blank=True, default='')


class PagarLiquidacionSerializer(serializers.Serializer):
    referencia_pago = serializers.CharField(required=False, allow_blank=True, default='')
    notas = serializers.CharField(required=False, allow_blank=True, default='')
