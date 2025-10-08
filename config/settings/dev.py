from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# CORS settings for development (allows all local ports)
CORS_ALLOW_ALL_ORIGINS = True

# Disable logging for simple development unless needed
LOGGING = {}