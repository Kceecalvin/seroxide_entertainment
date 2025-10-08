from .base import *

DEBUG = False

# SECURITY WARNING: Host header validation is critical in production!
# You must list your actual domain names here when deploying.
ALLOWED_HOSTS = ['seroxide.co.ke', 'www.seroxide.co.ke']

# Database configuration will be updated here for PostgreSQL/MySQL

# Security settings (crucial for production)
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
X_FRAME_OPTIONS = 'DENY'