from django.urls import path

from . import views, views_plataforma

urlpatterns = [
    path('tipo-cambio/', views.TipoCambioView.as_view(), name='tipo-cambio'),
    path('tipo-cambio/actualizar/', views.ActualizarTipoCambioView.as_view(), name='tipo-cambio-actualizar'),
    path('tiendas/<int:tienda_id>/gastos/', views.GastoListCreateView.as_view(), name='gastos-list-create'),
    path('tiendas/<int:tienda_id>/gastos/totales/', views.GastoTotalesView.as_view(), name='gastos-totales'),
    path('tiendas/<int:tienda_id>/gastos/<int:pk>/', views.GastoDetailView.as_view(), name='gastos-detail'),
    # CU-37: Planes de suscripción para empresas / propietarios de tiendas
    path('mi-suscripcion/', views_plataforma.MiSuscripcionEmpresaView.as_view(), name='mi-suscripcion'),
    path('mi-suscripcion/pago-intento/', views_plataforma.MiSuscripcionIntentoPagoView.as_view(), name='mi-suscripcion-pago-intento'),
    # CU-37: Planes de suscripción y liquidación de tiendas (Admin Plataforma)
    path('plataforma/planes/', views_plataforma.PlanSuscripcionListCreateView.as_view(), name='plataforma-planes'),
    path('plataforma/planes/<int:pk>/', views_plataforma.PlanSuscripcionDetailView.as_view(), name='plataforma-plan-detalle'),
    path('plataforma/suscripciones/', views_plataforma.SuscripcionesResumenView.as_view(), name='plataforma-suscripciones'),
    path('plataforma/tiendas/<int:tienda_id>/suscripcion/', views_plataforma.AsignarSuscripcionTiendaView.as_view(), name='plataforma-asignar-suscripcion'),
    path('plataforma/liquidaciones/previsualizar/', views_plataforma.LiquidacionPrevisualizarView.as_view(), name='plataforma-liquidacion-preview'),
    path('plataforma/liquidaciones/', views_plataforma.LiquidacionListCreateView.as_view(), name='plataforma-liquidaciones'),
    path('plataforma/liquidaciones/<int:pk>/<str:accion>/', views_plataforma.LiquidacionAccionView.as_view(), name='plataforma-liquidacion-accion'),
]
