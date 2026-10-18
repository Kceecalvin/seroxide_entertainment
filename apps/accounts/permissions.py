from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

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
scanner_required = roles_required('scanner', 'admin', 'superadmin')


def can_scan(user, event_id):
    return is_admin(user) or (role_for(user) == 'scanner' and user.gate_assignments.filter(event_id=event_id).exists())
