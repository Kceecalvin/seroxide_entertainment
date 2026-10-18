from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('order', 'phone_number', 'amount', 'status', 'mpesa_receipt_number', 'created_at')
    list_filter = ('status',)
    search_fields = ('order__reference', 'phone_number', 'mpesa_receipt_number', 'checkout_request_id')
    readonly_fields = (
        'order', 'phone_number', 'amount', 'checkout_request_id', 'merchant_request_id',
        'mpesa_receipt_number', 'result_code', 'result_desc', 'raw_callback', 'created_at', 'updated_at',
    )
