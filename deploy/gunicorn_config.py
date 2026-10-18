"""Gunicorn config for production. Referenced by deploy/serotix.service.

Worker count follows the standard (2 * CPU cores) + 1 formula, computed at
startup from the actual box — no hardcoded core count to go stale.
"""
import multiprocessing

bind = 'unix:/run/serotix/gunicorn.sock'
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
timeout = 30
graceful_timeout = 30
keepalive = 5

accesslog = '/var/log/serotix/gunicorn-access.log'
errorlog = '/var/log/serotix/gunicorn-error.log'
loglevel = 'info'
# Do not persist signed ticket links, lookup phone numbers or callback tokens.
# App errors and internal IDs provide diagnostics without logging request URLs.
access_log_format = '%(h)s %(t)s "%(m)s" %(s)s %(b)s %(L)s'

# Restart workers periodically to shed any slow memory growth — cheap
# insurance for a long-running production process.
max_requests = 1000
max_requests_jitter = 50
