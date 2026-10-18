from django import forms
from django.utils import timezone

from apps.events.models import Event, EventImage, LineupItem
from apps.tickets.models import TicketType

INPUT_CLASSES = (
    'mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white '
    'focus:border-brand-400 focus:outline-none focus:ring-1 focus:ring-brand-400'
)


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            'title', 'category', 'description', 'organizer_name',
            'venue', 'city', 'address', 'start_at', 'end_at',
            'cover_image', 'is_published', 'is_featured',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'category': forms.Select(attrs={'class': INPUT_CLASSES}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASSES, 'rows': 5}),
            'organizer_name': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'venue': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'city': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'address': forms.TextInput(attrs={'class': INPUT_CLASSES}),
            'start_at': forms.DateTimeInput(attrs={'class': INPUT_CLASSES, 'type': 'datetime-local'}),
            'end_at': forms.DateTimeInput(attrs={'class': INPUT_CLASSES, 'type': 'datetime-local'}),
            'cover_image': forms.ClearableFileInput(attrs={'class': 'mt-1 text-sm text-zinc-300'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # datetime-local inputs need "YYYY-MM-DDTHH:MM" — Django's default format won't match.
        for name in ('start_at', 'end_at'):
            if self.instance.pk and getattr(self.instance, name):
                self.initial[name] = timezone.localtime(getattr(self.instance, name)).strftime('%Y-%m-%dT%H:%M')


class TicketTypeForm(forms.ModelForm):
    class Meta:
        model = TicketType
        fields = ['name', 'description', 'price', 'quantity_total', 'max_per_order', 'is_active', 'sales_end']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'e.g. Regular, VIP'}),
            'description': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Optional'}),
            'price': forms.NumberInput(attrs={'class': INPUT_CLASSES, 'step': '0.01', 'min': '0'}),
            'quantity_total': forms.NumberInput(attrs={'class': INPUT_CLASSES, 'min': '0'}),
            'max_per_order': forms.NumberInput(attrs={'class': INPUT_CLASSES, 'min': '1'}),
            'sales_end': forms.DateTimeInput(attrs={'class': INPUT_CLASSES, 'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.sales_end:
            self.initial['sales_end'] = timezone.localtime(self.instance.sales_end).strftime('%Y-%m-%dT%H:%M')

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise forms.ValidationError('Paid tickets must have a price greater than zero.')
        return price

    def clean_max_per_order(self):
        value = self.cleaned_data['max_per_order']
        if not 1 <= value <= 50:
            raise forms.ValidationError('Choose between 1 and 50 tickets per order.')
        return value

    def clean_quantity_total(self):
        qty = self.cleaned_data['quantity_total']
        if self.instance.pk and qty < self.instance.quantity_sold:
            raise forms.ValidationError(
                f'Can\'t set total below {self.instance.quantity_sold} — that many are already sold.'
            )
        return qty


class EventImageForm(forms.ModelForm):
    class Meta:
        model = EventImage
        fields = ['image', 'caption']
        widgets = {
            'image': forms.ClearableFileInput(attrs={'class': 'mt-1 text-sm text-zinc-300'}),
            'caption': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Optional caption'}),
        }


class LineupItemForm(forms.ModelForm):
    class Meta:
        model = LineupItem
        fields = ['name', 'role', 'time', 'photo']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'Performer or speaker name'}),
            'role': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'e.g. Headliner, MC'}),
            'time': forms.TextInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'e.g. 9:00 PM'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'mt-1 text-sm text-zinc-300'}),
        }
