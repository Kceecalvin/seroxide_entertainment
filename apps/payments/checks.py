from django.conf import settings
from django.core.checks import Error, register
from .availability import available_methods


@register(deploy=True)
def live_payment_configuration(app_configs, **kwargs):
    if getattr(settings, 'PAYMENTS_REQUIRE_LIVE', False) and settings.PAYMENTS_LIVE and not available_methods():
        return [Error('PAYMENTS_LIVE is enabled without an available live provider.',
                      hint='Configure live M-Pesa or hosted Paystack, or set PAYMENTS_LIVE=0.',
                      id='payments.E001')]
    return []
