from django.core.management.base import BaseCommand
from apps.crm.models import CampanaCarrito
from apps.crm.services_carrito_abandonado import notificar_carritos_abandonados_tienda


class Command(BaseCommand):
    help = 'Bandeja/push para campañas de carrito; no modifica métricas de correo.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        total = 0
        for campana in CampanaCarrito.objects.filter(activo=True, tienda__activa=True).select_related('tienda'):
            total += notificar_carritos_abandonados_tienda(campana, dry_run=opts['dry_run'])
        self.stdout.write(f'Carritos {"previstos" if opts["dry_run"] else "notificados"}: {total}')
