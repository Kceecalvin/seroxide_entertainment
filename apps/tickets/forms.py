import re

from django import forms

PHONE_RE = re.compile(r'^(?:\+254|254|0)7\d{8}$|^(?:\+254|254|0)1\d{8}$')


class CheckoutForm(forms.Form):
    buyer_name = forms.CharField(max_length=150, label='Full name')
    buyer_email = forms.EmailField(required=False, label='Email (optional, for your receipt)')
    buyer_phone = forms.CharField(max_length=20, label='Phone number')
    payment_method = forms.ChoiceField(
        choices=[('mpesa', 'M-Pesa'), ('paystack', 'Card (Paystack)')],
        initial='mpesa',
    )
    # Only enforced for guest checkout (see views.checkout) — a signed-in buyer
    # already accepted these at signup, so re-asking every purchase is just
    # friction, not a meaningful extra consent.
    terms_accepted = forms.BooleanField(required=False)

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        if method in ('paystack', 'card') and not cleaned.get('buyer_email'):
            self.add_error('buyer_email', 'Enter your email for card payment and ticket delivery.')
        phone = cleaned.get('buyer_phone', '').strip().replace(' ', '')
        if not phone:
            self.add_error('buyer_phone', 'Enter a phone number.')
            return cleaned

        if method == 'mpesa':
            if not PHONE_RE.match(phone):
                self.add_error(
                    'buyer_phone', 'Enter a valid Safaricom number, e.g. 07XXXXXXXX or 2547XXXXXXXX.'
                )
            else:
                if phone.startswith('0'):
                    phone = '254' + phone[1:]
                elif phone.startswith('+'):
                    phone = phone[1:]
                cleaned['buyer_phone'] = phone
        else:
            # Card payment doesn't need a Safaricom number — still store whatever
            # phone the buyer gives us (used by the "find my tickets" lookup).
            cleaned['buyer_phone'] = phone.lstrip('+')

        return cleaned


class MyTicketsLookupForm(forms.Form):
    reference = forms.CharField(max_length=20, label='Order reference (e.g. SRX-AB12CD34)')
    buyer_phone = forms.CharField(max_length=20, label='Phone number used at checkout')


    def clean_buyer_phone(self):
        phone = self.cleaned_data['buyer_phone'].strip().replace(' ', '').lstrip('+')
        if not phone.isdigit() or not 9 <= len(phone) <= 15:
            raise forms.ValidationError('Enter the full phone number used at checkout.')
        return phone


class WaitlistForm(forms.Form):
    name = forms.CharField(max_length=150, label='Full name')
    email = forms.EmailField(label='Email')
    phone = forms.CharField(max_length=20, required=False, label='Phone (optional)')
