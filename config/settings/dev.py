from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '.loca.lt']  # .loca.lt: localtunnel, used for real webhook testing (M-Pesa/Stripe)

# CORS settings for development (allows all local ports)
CORS_ALLOW_ALL_ORIGINS = True

# Disable logging for simple development unless needed
LOGGING = {}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Local convenience only: simulate M-Pesa payments (instant "paid") unless the developer
# explicitly sets MPESA_SIMULATE=0 and provides real sandbox credentials in .env.
MPESA_SIMULATE = os.getenv('MPESA_SIMULATE', '1') == '1'
STRIPE_SIMULATE = os.getenv('STRIPE_SIMULATE', '1') == '1'
PAYSTACK_SIMULATE = os.getenv('PAYSTACK_SIMULATE', '1') == '1'
# Recompute — base.py already derived these from the *_SIMULATE vars before
# the overrides above ran, so the plain variable assignments there are stale here.
STRIPE_ENABLED = STRIPE_SIMULATE or bool(STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY and STRIPE_WEBHOOK_SECRET)
PAYSTACK_ENABLED = PAYSTACK_SIMULATE or bool(PAYSTACK_SECRET_KEY and PAYSTACK_PUBLIC_KEY)
