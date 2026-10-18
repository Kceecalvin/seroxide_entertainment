"""
Django settings for seroxide_entertainment project.
"""
from pathlib import Path
from decimal import Decimal
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'default-insecure-key-for-local-testing-only')

# Site branding, used by templates/context processor
SITE_NAME = os.getenv('SITE_NAME', 'SeroTix')
SITE_TAGLINE = os.getenv('SITE_TAGLINE', 'Tickets to Kenya’s best nights out.')
SITE_DOMAIN = os.getenv('SITE_DOMAIN', 'serotix.co.ke')
SITE_SUPPORT_EMAIL = os.getenv('SITE_SUPPORT_EMAIL', 'support@serotix.co.ke')
SITE_SUPPORT_PHONE = os.getenv('SITE_SUPPORT_PHONE', '0119 300000')
_support_digits = ''.join(c for c in SITE_SUPPORT_PHONE if c.isdigit())
SITE_SUPPORT_PHONE_TEL = '+' + ('254' + _support_digits[1:] if _support_digits.startswith('0') else _support_digits)

# --- Transactional email (ticket confirmations, contact form) ---
# dev.py overrides EMAIL_BACKEND to the console backend, so nothing here is
# needed for local dev; production sends through SMTP for real.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', '1') == '1'
DEFAULT_FROM_EMAIL = f'{SITE_NAME} <{SITE_SUPPORT_EMAIL}>'

# --- Socials (all optional — empty means "don't show this icon") ---
SOCIAL_INSTAGRAM = os.getenv('SOCIAL_INSTAGRAM', '')
SOCIAL_TIKTOK = os.getenv('SOCIAL_TIKTOK', '')
SOCIAL_TWITTER = os.getenv('SOCIAL_TWITTER', '')
SOCIAL_FACEBOOK = os.getenv('SOCIAL_FACEBOOK', '')
SOCIAL_WHATSAPP = os.getenv('SOCIAL_WHATSAPP', '')  # wa.me link or channel invite

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'corsheaders',   # For handling CORS (useful for API endpoints)
    'django.contrib.humanize',  # Human-friendly template filters (naturaltime, intcomma)
    'django.contrib.sitemaps',  # sitemap.xml for search engine discovery

    # Local apps
    'apps.events',
    'apps.accounts',
    'apps.core',
    'apps.tickets',
    'apps.payments',
    'apps.dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Serve static files without extra infra
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware', # Must be placed high
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.site_branding',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# Use the default SQLite for development, configured in dev.py/prod.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# LocMemCache is per-process — fine here (dev runs one process), but prod.py
# overrides this to a shared Redis/Valkey cache. apps/core/ratelimit.py's limits
# (checkout, waitlist, payment-status) rely on this cache being shared across
# every gunicorn worker; under LocMemCache each worker enforces its own separate
# limit, silently multiplying the real-world threshold by the worker count.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Nairobi' # Set for Kenya operations

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' # For production collection
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files (e.g., event images, ticket QR codes)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Staff-only views (the organizer dashboard, ticket check-in) send unauthenticated
# visitors to the branded dashboard login (templates/dashboard/login.html), not
# Django's generic default admin login page.
LOGIN_URL = 'dashboard:login'
LOGIN_REDIRECT_URL = 'dashboard:home'

# How many reverse-proxy hops in front of this app actually append to
# X-Forwarded-For (nginx, a load balancer, etc). 0 = don't trust the header at
# all — apps/core/ratelimit.py falls back to REMOTE_ADDR, which is the safe
# default for a direct/gunicorn-only deployment. Only raise this to match the
# real proxy topology in production, or the rate limiter becomes spoofable.
TRUSTED_PROXY_COUNT = int(os.getenv('TRUSTED_PROXY_COUNT', '0'))

# --- M-Pesa Daraja API (apps/payments/mpesa.py) ---
MPESA_ENV = os.getenv('MPESA_ENV', 'sandbox')  # 'sandbox' or 'production'
MPESA_CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY', '')
MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET', '')
MPESA_SHORTCODE = os.getenv('MPESA_SHORTCODE', '174379')  # Daraja sandbox default test shortcode
MPESA_PASSKEY = os.getenv('MPESA_PASSKEY', '')
MPESA_CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL', '')
# A random path segment that must appear in the callback URL (see config/urls.py /
# apps/payments/urls.py) — Safaricom's webhook is otherwise unauthenticated, so this
# stops anyone who doesn't know the URL from posting fake "payment succeeded" events.
MPESA_CALLBACK_TOKEN = os.getenv('MPESA_CALLBACK_TOKEN', '')

# Explicit opt-in only — simulated payments must never turn on just because credentials
# happen to be missing (that would silently hand out free tickets on a misconfigured
# production deploy). dev.py defaults this on for local convenience; prod.py forbids it.
MPESA_SIMULATE = os.getenv('MPESA_SIMULATE', '') == '1'
PAYMENTS_LIVE = os.getenv('PAYMENTS_LIVE', '0') == '1'
PAYMENTS_REQUIRE_LIVE = False  # production overrides; isolated tests may simulate

# New purchases: organizer receives 95% of ticket value. SeroTix covers
# processing from its 5% commission. Old SERVICE_FEE_PERCENT env values are
# deliberately ignored; historical order fees remain unchanged in the DB.
PLATFORM_COMMISSION_RATE = Decimal('0.05')

# --- Stripe (apps/payments/stripe_client.py) — card payments alongside M-Pesa ---
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')

# Same explicit-opt-in reasoning as MPESA_SIMULATE above.
STRIPE_SIMULATE = os.getenv('STRIPE_SIMULATE', '') == '1'

# Card payment is optional (M-Pesa is the primary rail for this Kenya-focused
# platform) — the checkout only offers it once real keys are configured.
STRIPE_ENABLED = STRIPE_SIMULATE or bool(STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY and STRIPE_WEBHOOK_SECRET)

# --- Paystack (apps/payments/paystack_client.py) — replaced Stripe for card
# payments: Stripe doesn't support creating an account for a Kenya-based
# business at all, so it could never go live here. Paystack (Stripe-owned,
# but a separate product) directly supports Kenya. ---
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', '')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', '')

# Same explicit-opt-in reasoning as MPESA_SIMULATE/STRIPE_SIMULATE above.
PAYSTACK_SIMULATE = os.getenv('PAYSTACK_SIMULATE', '') == '1'

PAYSTACK_ENABLED = PAYSTACK_SIMULATE or bool(PAYSTACK_SECRET_KEY and PAYSTACK_PUBLIC_KEY)

# Flutterwave Direct Charge (2D Visa/Mastercard — no 3DS redirect).
# Get keys from: https://dashboard.flutterwave.com/dashboard/settings/apis
FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY', '')
FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY', '')
# Webhook hash set in Flutterwave dashboard → Settings → Webhooks → Secret hash.
FLUTTERWAVE_WEBHOOK_HASH = os.getenv('FLUTTERWAVE_WEBHOOK_HASH', '')
FLUTTERWAVE_SIMULATE = os.getenv('FLUTTERWAVE_SIMULATE', '') == '1'
FLUTTERWAVE_ENABLED = False  # direct-card handling is retired; use hosted checkout

EMAIL_TIMEOUT = 10
PASSWORD_RESET_TIMEOUT = 3600
