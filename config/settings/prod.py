import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False
PAYMENTS_REQUIRE_LIVE = True
LOCAL_DEMO_ENABLED = False

# SECURITY WARNING: Host header validation is critical in production!
ALLOWED_HOSTS = [h for h in os.getenv(
    'DJANGO_ALLOWED_HOSTS', 'serotix.co.ke,www.serotix.co.ke'
).split(',') if h]

# Production requires a real, concurrent-write-capable database. SQLite's
# select_for_update() is a silent no-op (single-writer, no row locking) —
# every stock-reservation and payment-idempotency guard in this app depends
# on real row locks, so running prod on SQLite would quietly defeat them.
_database_url = os.getenv('DATABASE_URL', '')
if not _database_url:
    raise ImproperlyConfigured(
        'DATABASE_URL must be set in production (e.g. postgres://user:pass@host:5432/dbname) — '
        'SQLite cannot safely back concurrent payment/check-in operations.'
    )
_parsed_db = urlparse(_database_url)
if _parsed_db.scheme not in ('postgres', 'postgresql'):
    raise ImproperlyConfigured(
        f'Unsupported DATABASE_URL scheme "{_parsed_db.scheme}" — use postgres:// in production.'
    )
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _parsed_db.path.lstrip('/'),
        'USER': _parsed_db.username,
        'PASSWORD': _parsed_db.password,
        'HOST': _parsed_db.hostname,
        'PORT': _parsed_db.port or 5432,
        'CONN_MAX_AGE': 60,
    }
}

# Production runs gunicorn with several worker processes — base.py's LocMemCache
# is per-process, so each worker would enforce its own separate rate limit
# (apps/core/ratelimit.py), multiplying the real-world threshold by the worker
# count. REDIS_URL must point at a cache shared by every worker.
_redis_url = os.getenv('REDIS_URL', '')
if not _redis_url:
    raise ImproperlyConfigured(
        'REDIS_URL must be set in production (e.g. redis://127.0.0.1:6379/1) — '
        'without a shared cache, apps/core/ratelimit.py enforces its limits per '
        'gunicorn worker instead of globally, silently weakening every rate limit.'
    )
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': _redis_url,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    }
}

# Security settings (crucial for production)
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7  # 7 days, ramp up once DNS/TLS is confirmed stable
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Nginx terminates TLS and proxies to gunicorn over plain HTTP internally
# (see deploy/nginx.conf) — without this, Django sees every request as
# insecure HTTP and SECURE_SSL_REDIRECT above would redirect-loop forever,
# since nginx never re-terminates the already-secure connection it forwards.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Serve compressed, cache-busted static assets without a separate CDN/web server.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# --- Fail loudly instead of silently degrading (see security review notes) ---
if not SECRET_KEY or SECRET_KEY == 'default-insecure-key-for-local-testing-only':
    raise ImproperlyConfigured('SECRET_KEY environment variable must be set in production.')

if MPESA_SIMULATE:
    raise ImproperlyConfigured(
        'MPESA_SIMULATE must never be enabled in production — it issues tickets with no real payment.'
    )

_missing_mpesa = [
    name for name, value in [
        ('MPESA_CONSUMER_KEY', MPESA_CONSUMER_KEY),
        ('MPESA_CONSUMER_SECRET', MPESA_CONSUMER_SECRET),
        ('MPESA_PASSKEY', MPESA_PASSKEY),
        ('MPESA_CALLBACK_URL', MPESA_CALLBACK_URL),
        ('MPESA_CALLBACK_TOKEN', MPESA_CALLBACK_TOKEN),
    ] if not value
]
if _missing_mpesa:
    raise ImproperlyConfigured(f'Missing required M-Pesa settings in production: {", ".join(_missing_mpesa)}')

_missing_email = [
    name for name, value in [
        ('EMAIL_HOST', EMAIL_HOST),
        ('EMAIL_HOST_USER', EMAIL_HOST_USER),
        ('EMAIL_HOST_PASSWORD', EMAIL_HOST_PASSWORD),
    ] if not value
]
if _missing_email:
    raise ImproperlyConfigured(
        f'Missing required email settings in production: {", ".join(_missing_email)} — '
        'without these, ticket confirmations and the contact form fail silently.'
    )

if STRIPE_SIMULATE:
    raise ImproperlyConfigured(
        'STRIPE_SIMULATE must never be enabled in production — it issues tickets with no real payment.'
    )

# Stripe itself is optional in prod (M-Pesa alone is a valid deployment), but a
# *partial* set of keys is always a misconfiguration worth failing loudly on
# rather than silently running with card payments half-broken.
_stripe_keys = {
    'STRIPE_SECRET_KEY': STRIPE_SECRET_KEY,
    'STRIPE_PUBLISHABLE_KEY': STRIPE_PUBLISHABLE_KEY,
    'STRIPE_WEBHOOK_SECRET': STRIPE_WEBHOOK_SECRET,
}
_stripe_present = [name for name, value in _stripe_keys.items() if value]
if _stripe_present and len(_stripe_present) != len(_stripe_keys):
    _missing_stripe = [name for name, value in _stripe_keys.items() if not value]
    raise ImproperlyConfigured(f'Partial Stripe configuration in production: missing {", ".join(_missing_stripe)}')

if PAYSTACK_SIMULATE:
    raise ImproperlyConfigured(
        'PAYSTACK_SIMULATE must never be enabled in production — it issues tickets with no real payment.'
    )

if FLUTTERWAVE_SIMULATE:
    raise ImproperlyConfigured('FLUTTERWAVE_SIMULATE must never be enabled in production.')

_paystack_keys = {
    'PAYSTACK_SECRET_KEY': PAYSTACK_SECRET_KEY,
    'PAYSTACK_PUBLIC_KEY': PAYSTACK_PUBLIC_KEY,
}
_paystack_present = [name for name, value in _paystack_keys.items() if value]
if _paystack_present and len(_paystack_present) != len(_paystack_keys):
    _missing_paystack = [name for name, value in _paystack_keys.items() if not value]
    raise ImproperlyConfigured(f'Partial Paystack configuration in production: missing {", ".join(_missing_paystack)}')
