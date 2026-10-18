from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import AccountProfile


def role_for(user):
    if not user.is_authenticated or not user.is_active:
        return 'anonymous'
    if user.is_superuser:
        return 'superadmin'
    try:
        return user.account_profile.role
    except AccountProfile.DoesNotExist:
        # Preserve legacy door accounts; event assignment is still required.
        return 'scanner' if user.is_staff else 'buyer'


def is_admin(user):
    return role_for(user) in ('admin', 'superadmin')


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), 'accounts:login')
            if role_for(request.user) not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


admin_required = roles_required('admin', 'superadmin')
seller_required = roles_required('seller')
def gate_assignments(user, *, active=False):
    assignments = user.gate_assignments.filter(revoked_at__isnull=True, ends_at__gt=timezone.now())
    return assignments.filter(starts_at__lte=timezone.now()) if active else assignments


def has_gate_access(user):
    if not user.is_authenticated or not user.is_active:
        return False
    return is_admin(user) or role_for(user) == 'scanner' or user.gate_assignments.exists() or user.seller_events.exists()


def scanner_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), 'accounts:login')
        if not has_gate_access(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def can_manage_gate(user, event):
    return user.is_authenticated and user.is_active and (is_admin(user) or event.owner_id == user.pk)


def can_scan(user, event_id):
    if not user.is_authenticated or not user.is_active:
        return False
    return is_admin(user) or user.seller_events.filter(pk=event_id).exists() or gate_assignments(user, active=True).filter(event_id=event_id).exists()


def can_supervise(user, event):
    return can_manage_gate(user, event) or (user.is_authenticated and user.is_active and gate_assignments(user, active=True).filter(event=event, is_supervisor=True).exists())
