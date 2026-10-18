from django.contrib import admin

from .models import Event, EventImage, LineupItem


class TicketTypeInline(admin.TabularInline):
    from apps.tickets.models import TicketType
    model = TicketType
    extra = 1
    fields = ('name', 'price', 'quantity_total', 'quantity_sold', 'is_active', 'sales_end')
    readonly_fields = ('quantity_sold',)


class EventImageInline(admin.TabularInline):
    model = EventImage
    extra = 1
    fields = ('image', 'caption', 'order')


class LineupItemInline(admin.TabularInline):
    model = LineupItem
    extra = 1
    fields = ('name', 'role', 'time', 'photo', 'order')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'venue', 'city', 'start_at', 'is_published', 'is_featured')
    list_filter = ('category', 'city', 'is_published', 'is_featured')
    search_fields = ('title', 'venue', 'city', 'description')
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'start_at'
    inlines = [TicketTypeInline, EventImageInline, LineupItemInline]
