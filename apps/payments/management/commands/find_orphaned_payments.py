"""Find payments where money was confirmed received but no ticket exists.

Normally impossible — fulfill_order() runs synchronously right after a
payment is marked COMPLETED. But if fulfill_order() ever throws (a bug, a
DB hiccup, anything) *after* that COMPLETED write has already committed,
the payment record shows money received while the order stays unpaid with
no tickets minted. This command finds exactly that mismatch so it can be
fixed by hand (retry fulfilment, or refund) rather than going unnoticed.

Not wired to a scheduler — run it periodically yourself, same as
expire_stale_orders (see apps/tickets/management/commands/expire_stale_orders.py):
    */15 * * * * cd /path/to/project && venv/bin/python manage.py find_orphaned_payments
"""
from django.core.management.base import BaseCommand

from apps.payments.models import Payment, PaymentStatus
from apps.tickets.models import OrderStatus


class Command(BaseCommand):
    help = 'List completed payments whose order has no valid tickets — money received, nothing issued.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--retry', action='store_true',
            help='Attempt to re-run fulfil_order() for each orphaned payment found.',
        )

    def handle(self, *args, **options):
        orphaned = (
            Payment.objects.filter(status=PaymentStatus.COMPLETED)
            .exclude(order__status=OrderStatus.PAID)
            .select_related('order')
        )

        count = orphaned.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No orphaned payments found — every completed payment has a paid order.'))
            return

        self.stdout.write(self.style.WARNING(f'{count} orphaned payment(s) found — money received, order not fulfilled:'))
        for payment in orphaned:
            receipt = payment.mpesa_receipt_number or payment.stripe_payment_intent_id or '(no receipt on file)'
            self.stdout.write(
                f'  order={payment.order.reference}  amount=KES {payment.amount}  '
                f'method={payment.method}  receipt={receipt}  order_status={payment.order.status}'
            )

        if options['retry']:
            from apps.tickets.services import fulfill_order
            self.stdout.write('')
            for payment in orphaned:
                try:
                    fulfill_order(payment.order)
                    self.stdout.write(self.style.SUCCESS(f'  Fixed: {payment.order.reference} now fulfilled.'))
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f'  Still failing for {payment.order.reference}: {exc}'))
