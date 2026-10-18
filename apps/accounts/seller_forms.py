from django import forms
from django.utils import timezone
from apps.dashboard.forms import EventForm, TicketTypeForm as BaseTicketTypeForm
from apps.events.models import Event


class SellerEventForm(EventForm):
    class Meta(EventForm.Meta):
        fields = [f for f in EventForm.Meta.fields if f not in ('is_published', 'is_featured')] + ['theme']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['theme'].required = False
        labels = {'title': 'Event name', 'description': 'What should guests expect?',
                  'start_at': 'Starts (Nairobi time)', 'end_at': 'Ends (Nairobi time)',
                  'organizer_name': 'Organizer name', 'cover_image': 'Event poster / cover'}
        for name, label in labels.items():
            self.fields[name].label = label
        self.fields['cover_image'].help_text = 'JPG, PNG or WebP, up to 5 MB. You can add this later.'
        self.fields['cover_image'].widget.attrs['accept'] = 'image/jpeg,image/png,image/webp'
        self.fields['title'].widget.attrs['placeholder'] = 'e.g. Nairobi Live Sessions'
        self.fields['description'].widget.attrs['placeholder'] = 'The experience, who it’s for, and what’s included.'

    def clean_theme(self):
        return self.cleaned_data.get('theme') or Event.Theme.CLASSIC

    def clean(self):
        data = super().clean()
        start, end = data.get('start_at'), data.get('end_at')
        if start and start <= timezone.now():
            self.add_error('start_at', 'Choose a future date.')
        if start and end and end <= start:
            self.add_error('end_at', 'The end must be after the start.')
        return data

    def clean_cover_image(self):
        image = self.cleaned_data.get('cover_image')
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Choose an image smaller than 5 MB.')
        return image


class SellerOnboardingForm(forms.Form):
    business_name = forms.CharField(max_length=150, label='Organizer / business name')
    accepted = forms.BooleanField(label='I agree to the Terms of Service and confirm that my event details will be accurate.')


class TicketTypeForm(BaseTicketTypeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].label = 'Price (KES)'
        self.fields['quantity_total'].label = 'Number of tickets'
        self.fields['max_per_order'].label = 'Maximum per order'
        self.fields['sales_end'].label = 'Sales close (Nairobi time)'
