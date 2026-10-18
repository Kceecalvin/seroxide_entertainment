from django import forms
from django.utils import timezone
from apps.dashboard.forms import EventForm, TicketTypeForm
from apps.events.models import Event


class SellerEventForm(EventForm):
    class Meta(EventForm.Meta):
        fields = [f for f in EventForm.Meta.fields if f not in ('is_published', 'is_featured')]

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
