from django.contrib import admin

from .models import Order, OrderItem, Ticket, TicketType


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('ticket_type', 'quantity', 'unit_price')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('reference', 'event', 'buyer_name', 'buyer_phone', 'status', 'total_amount', 'created_at')
    list_filter = ('status', 'event')
    search_fields = ('reference', 'buyer_name', 'buyer_phone', 'buyer_email')
    readonly_fields = ('reference', 'total_amount', 'created_at', 'updated_at', 'paid_at')
    inlines = [OrderItemInline]


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ('event', 'name', 'price', 'quantity_total', 'quantity_sold', 'remaining', 'is_active')
    list_filter = ('is_active', 'event')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('serial', 'event', 'ticket_type', 'status', 'checked_in_at')
    list_filter = ('status',)
    search_fields = ('serial',)
    readonly_fields = ('serial', 'qr_code')
