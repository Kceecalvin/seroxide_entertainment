"""Safe readiness report: no credentials, recipients or raw payment references."""
import json
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone
from apps.core.models import EmailDelivery
from apps.events.models import Event
from apps.payments.availability import available_methods
from apps.payments.models import Payment


class Command(BaseCommand):
    help = 'Report production health and owner activation tasks without secrets.'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help='Fail on dependency errors or unfulfilled completed payments.')

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        cache.set('serotix:readiness', 'ok', timeout=30)
        cache_ok = cache.get('serotix:readiness') == 'ok'
        unmatched = Payment.objects.filter(status='completed').exclude(order__status='paid').count()
        result = {
            'checked_at': timezone.now().isoformat(), 'database': connection.vendor,
            'cache_ok': cache_ok, 'checkout_methods': available_methods(),
            'payments_live_switch': settings.PAYMENTS_LIVE,
            'upcoming_events': Event.objects.filter(is_published=True, start_at__gte=timezone.now()).count(),
            'unfulfilled_completed_payments': unmatched,
            'failed_emails': EmailDelivery.objects.filter(status='failed').count(),
            'pending_emails': EmailDelivery.objects.filter(status='pending').count(),
        }
        self.stdout.write(json.dumps(result, indent=2))
        if options['check'] and (not cache_ok or unmatched):
            raise CommandError('Production dependencies or payment reconciliation need attention.')
