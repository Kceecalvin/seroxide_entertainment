"""Release stock reserved by orders that never completed payment.

create_order() reserves stock immediately (see apps/tickets/services.py) so
concurrent buyers can't oversell the same last-few tickets. That reservation
is released automatically when a payment provider reports failure — but an
order abandoned mid-checkout (STK prompt ignored, tab closed, callback lost)
never gets that signal, so its stock would stay reserved forever without
this cleanup.

Not wired to a scheduler — run it periodically yourself (cron / systemd timer
/ your host's scheduled-jobs feature), e.g. every 5 minutes:
    */5 * * * * cd /path/to/project && venv/bin/python manage.py expire_stale_orders
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tickets.models import Order, OrderStatus
from apps.tickets.services import release_order_stock

DEFAULT_STALE_MINUTES = 30  # generous — well past any STK prompt's own ~90s expiry


class Command(BaseCommand):
    help = 'Release stock reserved by PENDING orders older than --minutes (default 30) and mark them expired.'

    def add_arguments(self, parser):
        parser.add_argument('--minutes', type=int, default=DEFAULT_STALE_MINUTES)
        parser.add_argument('--dry-run', action='store_true', help="Show what would be expired without changing anything.")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timezone.timedelta(minutes=options['minutes'])
        stale = Order.objects.filter(status=OrderStatus.PENDING, created_at__lt=cutoff)

        count = stale.count()
        if count == 0:
            self.stdout.write('No stale pending orders found.')
            return

        if options['dry_run']:
            for order in stale:
                self.stdout.write(f'Would expire {order.reference} (created {order.created_at:%Y-%m-%d %H:%M})')
            self.stdout.write(self.style.WARNING(f'{count} order(s) would be expired (dry run, nothing changed).'))
            return

        expired = 0
        for order in stale:
            release_order_stock(order, new_status=OrderStatus.EXPIRED)
            expired += 1

        self.stdout.write(self.style.SUCCESS(f'Expired {expired} stale pending order(s), stock released.'))
