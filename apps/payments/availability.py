"""One server-side policy for payment buttons, checkout and provider initiation."""
from django.conf import settings


def available_methods():
    live = getattr(settings, 'PAYMENTS_REQUIRE_LIVE', False)
    if live and not getattr(settings, 'PAYMENTS_LIVE', False):
        return ()
    methods = []
    mpesa_configured = all(getattr(settings, key, '') for key in (
        'MPESA_CONSUMER_KEY', 'MPESA_CONSUMER_SECRET', 'MPESA_PASSKEY',
        'MPESA_SHORTCODE', 'MPESA_CALLBACK_URL', 'MPESA_CALLBACK_TOKEN'))
    if ((not live and settings.MPESA_SIMULATE) or
            (mpesa_configured and (not live or settings.MPESA_ENV == 'production'))):
        methods.append('mpesa')
    paystack_configured = bool(settings.PAYSTACK_SECRET_KEY and settings.PAYSTACK_PUBLIC_KEY)
    paystack_live = (settings.PAYSTACK_SECRET_KEY.startswith('sk_live_') and
                     settings.PAYSTACK_PUBLIC_KEY.startswith('pk_live_'))
    if ((not live and settings.PAYSTACK_SIMULATE) or
            (paystack_configured and (not live or paystack_live))):
        methods.append('paystack')
    return tuple(methods)


def require_method(method):
    if method not in available_methods():
        raise ValueError('This payment method is not available.')
