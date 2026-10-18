"""Role split: `is_staff` alone (Django's admin/dashboard access flag) is not
enough granularity for this app — a door scanner and a full event/pricing
admin need very different levels of trust. Convention used everywhere:

  - is_staff=True, is_superuser=False -> "gateman": can reach the scanner
    (apps/tickets/views.py: scanner, scanner_check, verify_ticket — still
    gated by Django's own @staff_member_required) and nothing else staff-only.
  - is_superuser=True (implies is_staff=True by convention) -> full access,
    including the organizer dashboard (apps/dashboard/views.py, all gated
    by @superuser_required below) and Django admin.
"""
import functools

from django.contrib.auth.views import redirect_to_login


def superuser_required(view_func=None, *, login_url='dashboard:login'):
    """Same shape as django.contrib.admin.views.decorators.staff_member_required,
    but requires is_superuser rather than just is_staff — use this (not
    @staff_member_required) for anything beyond ticket scanning."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapped(request, *args, **kwargs):
            if request.user.is_active and request.user.is_superuser:
                return fn(request, *args, **kwargs)
            return redirect_to_login(request.get_full_path(), login_url)
        return wrapped
    if view_func:
        return decorator(view_func)
    return decorator
