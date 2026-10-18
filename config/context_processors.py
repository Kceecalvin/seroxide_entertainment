from django.conf import settings


def site_branding(request):
    """Expose site-wide branding constants to every template."""
    from apps.accounts.permissions import role_for
    role = role_for(request.user)
    from apps.payments.availability import available_methods
    methods = available_methods()
    return {
        'account_role': role,
        'LOCAL_DEMO': getattr(settings, 'LOCAL_DEMO_ENABLED', False) and settings.DEBUG,
        'platform_admin': role in ('admin', 'superadmin'),
        'SITE_NAME': settings.SITE_NAME,
        'SITE_TAGLINE': settings.SITE_TAGLINE,
        'SITE_SUPPORT_EMAIL': settings.SITE_SUPPORT_EMAIL,
        'SITE_SUPPORT_PHONE': settings.SITE_SUPPORT_PHONE,
        'SITE_DOMAIN': settings.SITE_DOMAIN,
        'PAYSTACK_ENABLED': 'paystack' in methods,
        'MPESA_ENABLED': 'mpesa' in methods,
        'CHECKOUT_AVAILABLE': bool(methods),
        'SOCIAL_INSTAGRAM': settings.SOCIAL_INSTAGRAM,
        'SOCIAL_TIKTOK': settings.SOCIAL_TIKTOK,
        'SOCIAL_TWITTER': settings.SOCIAL_TWITTER,
        'SOCIAL_FACEBOOK': settings.SOCIAL_FACEBOOK,
        'SOCIAL_WHATSAPP': settings.SOCIAL_WHATSAPP,
    }
