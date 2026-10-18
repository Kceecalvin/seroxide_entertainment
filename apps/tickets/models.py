import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils.crypto import get_random_string


class TicketType(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='ticket_types')
    name = models.CharField(max_length=100)  # e.g. "Regular", "VIP", "Early Bird"
    description = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_total = models.PositiveIntegerField()
    quantity_sold = models.PositiveIntegerField(default=0)
    max_per_order = models.PositiveSmallIntegerField(default=8)
    is_active = models.BooleanField(default=True)
    sales_end = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f'{self.event.title} — {self.name}'

    @property
    def remaining(self):
        return max(self.quantity_total - self.quantity_sold, 0)


class WaitlistEntry(models.Model):
    """Captures demand a sold-out tier would otherwise just lose. Notified
    (see apps.tickets.services.notify_waitlist) the moment stock frees up
    from a refund or an abandoned/cancelled pending order — first-come,
    first-served on actually completing checkout, same as any real sale."""
    ticket_type = models.ForeignKey(TicketType, on_delete=models.CASCADE, related_name='waitlist_entries')
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.name} — {self.ticket_type}'


def generate_order_reference():
    return f'SRX-{get_random_string(8, allowed_chars="ABCDEFGHJKLMNPQRSTUVWXYZ23456789")}'


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Awaiting payment'
    PAID = 'paid', 'Paid'
    CANCELLED = 'cancelled', 'Cancelled'
    EXPIRED = 'expired', 'Expired'


class Order(models.Model):
    reference = models.CharField(max_length=20, unique=True, default=generate_order_reference, editable=False)
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='orders')
    # Optional — guest checkout (no account) stays fully supported. When the
    # buyer is signed in at checkout, this links the order to their account
    # so it shows up automatically on their My Account page.
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders'
    )

    buyer_name = models.CharField(max_length=150)
    buyer_email = models.EmailField(blank=True)
    buyer_phone = models.CharField(max_length=20)

    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    # total_amount is what's actually charged (tickets + fee) — the number
    # every payment call and every "amount to pay" template already uses.
    # service_fee is broken out separately purely for display/audit — see
    # settings.SERVICE_FEE_PERCENT and templates/legal/terms.html's
    # "no hidden fees beyond what's displayed at checkout" promise.
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.reference

    @property
    def subtotal_amount(self):
        return self.total_amount - self.service_fee

    def recalculate_total(self):
        subtotal = sum(item.subtotal for item in self.items.all())
        fee_rate = Decimal(str(settings.SERVICE_FEE_PERCENT))
        self.service_fee = (subtotal * fee_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.total_amount = subtotal + self.service_fee
        self.save(update_fields=['service_fee', 'total_amount'])
        return self.total_amount


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name='order_items')
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


class TicketStatus(models.TextChoices):
    VALID = 'valid', 'Valid'
    USED = 'used', 'Checked in'
    CANCELLED = 'cancelled', 'Cancelled'


class Ticket(models.Model):
    checked_in_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='checked_in_tickets')
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='tickets')
    serial = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    qr_code = models.ImageField(upload_to='tickets/qr/', blank=True)
    status = models.CharField(max_length=20, choices=TicketStatus.choices, default=TicketStatus.VALID)
    checked_in_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'Ticket {self.serial}'

    @property
    def event(self):
        return self.order_item.order.event

    @property
    def ticket_type(self):
        return self.order_item.ticket_type

    @property
    def order(self):
        return self.order_item.order
