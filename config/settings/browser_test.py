"""Isolated local browser verification: never connects to real payment providers."""
from .dev import *

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': '/tmp/serotix-browser-tests.sqlite3'}}
MEDIA_ROOT = Path('/tmp/serotix-browser-test-media')
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
MPESA_SIMULATE = True
STRIPE_SIMULATE = True
PAYSTACK_SIMULATE = True
STRIPE_ENABLED = True
PAYSTACK_ENABLED = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']

# Explicitly isolated demo tools; never enabled in dev/prod settings.
LOCAL_DEMO_ENABLED = True

# Demo refund actions must never contact card providers.
REFUNDS_SIMULATE = True
