from django.db import models


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    REFUNDED = 'refunded', 'Refunded'


class PaymentMethod(models.TextChoices):
    MPESA = 'mpesa', 'M-Pesa'
    STRIPE = 'stripe', 'Card (Stripe)'  # retired — kept for existing Payment rows, no longer offered at checkout
    PAYSTACK = 'paystack', 'Card (Paystack)'
    FLUTTERWAVE = 'flutterwave', 'Card (Visa/Mastercard)'


class Payment(models.Model):
    order = models.ForeignKey('tickets.Order', on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=15, choices=PaymentMethod.choices, default=PaymentMethod.MPESA)
    phone_number = models.CharField(max_length=20, blank=True)  # M-Pesa only
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # M-Pesa
    checkout_request_id = models.CharField(max_length=100, blank=True, db_index=True)
    merchant_request_id = models.CharField(max_length=100, blank=True)
    mpesa_receipt_number = models.CharField(max_length=50, blank=True)

    # Stripe
    stripe_session_id = models.CharField(max_length=120, blank=True, db_index=True)
    stripe_payment_intent_id = models.CharField(max_length=120, blank=True)

    # Paystack — order.reference alone can't be reused as Paystack's own
    # `reference` if an order gets a second payment attempt (Paystack requires
    # it unique per transaction), so this is its own field, set once the
    # Payment row (and its pk) exists.
    paystack_reference = models.CharField(max_length=120, blank=True, db_index=True)

    # Flutterwave — tx_ref is our unique reference per attempt (same uniqueness
    # concern as Paystack); flw_tx_id is Flutterwave's own numeric transaction ID,
    # needed for refunds and verification calls.
    flw_tx_ref = models.CharField(max_length=120, blank=True, db_index=True)
    flw_tx_id = models.CharField(max_length=40, blank=True)

    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    result_code = models.CharField(max_length=10, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    raw_callback = models.JSONField(blank=True, null=True)

    # Refunds — Stripe's is a real refund id from their API; M-Pesa has no
    # simple merchant-refund endpoint via Daraja (that needs the separate B2C
    # product), so this holds the Safaricom transaction code a staff member
    # enters after sending the money back manually through Safaricom's own
    # tools. See apps/payments/refunds.py.
    refunded_at = models.DateTimeField(blank=True, null=True)
    refund_reference = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Payment #{self.pk} for {self.order.reference} ({self.status})'
