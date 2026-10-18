from django import forms
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class SignupForm(forms.Form):
    intent = forms.ChoiceField(choices=[('buyer', 'Discover & buy tickets'), ('seller', 'Host & sell tickets')], initial='buyer', required=False, widget=forms.RadioSelect)

    full_name = forms.CharField(max_length=150, label='Full name')
    email = forms.EmailField(label='Email')
    password = forms.CharField(widget=forms.PasswordInput, label='Password')
    terms_accepted = forms.BooleanField(
        required=True,
        error_messages={'required': 'You need to accept the Terms of Service and Privacy Policy to continue.'},
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            raise forms.ValidationError('An account with this email already exists — try logging in instead.')
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        # Uses Django's configured AUTH_PASSWORD_VALIDATORS (min length, not
        # entirely numeric, not too common/similar to the email) — same bar
        # as the staff dashboard accounts, not a weaker one for buyers.
        validate_password(password)
        return password

    def save(self):
        email = self.cleaned_data['email']
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data['password'],
            first_name=first_name[:150],
            last_name=last_name[:150],
        )
        return user


class ProfileForm(forms.ModelForm):
    """Editable account details. Email doubles as username (see SignupForm),
    so changing it here updates both — the alternative (letting them drift
    apart) makes login confusing about which value actually works."""
    full_name = forms.CharField(max_length=150, label='Full name')

    class Meta:
        model = User
        fields = ['email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        full_name = f'{self.instance.first_name} {self.instance.last_name}'.strip()
        self.fields['full_name'].initial = full_name
        self.fields['email'].label = 'Email'
        self.order_fields(['full_name', 'email'])

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Another account already uses this email.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data['full_name'].strip()
        first_name, _, last_name = full_name.partition(' ')
        user.first_name = first_name[:150]
        user.last_name = last_name[:150]
        user.username = user.email
        if commit:
            user.save()
        return user


from django.contrib.auth.forms import PasswordResetForm, AuthenticationForm
from django.conf import settings
from django.template.loader import render_to_string
from apps.core.mailer import queue_email


class AccountAuthenticationForm(AuthenticationForm):
    def clean_username(self):
        value = self.cleaned_data['username'].strip()
        match = User.objects.filter(username__iexact=value).first()
        return match.username if match else value


class TrackedPasswordResetForm(PasswordResetForm):
    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        context.update({'site_name': settings.SITE_NAME, 'site_domain': settings.SITE_DOMAIN,
                        'domain': settings.SITE_DOMAIN, 'protocol': 'https', 'scheme': 'https',
                        'support_email': settings.SITE_SUPPORT_EMAIL})
        queue_email(recipient=to_email, subject='Reset your SeroTix password',
            text=render_to_string(email_template_name, context),
            html=render_to_string(html_email_template_name, context) if html_email_template_name else '')
