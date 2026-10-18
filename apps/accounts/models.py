from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import timedelta


def default_shift_end():
    return timezone.now() + timedelta(hours=12)


class AccountProfile(models.Model):
    class Role(models.TextChoices):
        BUYER = 'buyer', 'Buyer'
        SELLER = 'seller', 'Seller'
        ADMIN = 'admin', 'Admin'
        SCANNER = 'scanner', 'Gate scanner'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='account_profile')
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.BUYER)
    business_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GateAssignment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gate_assignments')
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='gate_assignments')
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(default=default_shift_end)
    gate_label = models.CharField(max_length=80, default='Main gate')
    is_supervisor = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    @property
    def access_status(self):
        if self.revoked_at:
            return 'Revoked'
        if self.ends_at <= timezone.now():
            return 'Expired'
        if self.starts_at > timezone.now():
            return 'Scheduled'
        return 'Active'

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'event'], name='unique_event_scanner'),
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='gate_shift_positive'),
        ]


class GateInvitation(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='gate_invitations')
    email = models.EmailField()
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    gate_label = models.CharField(max_length=80, default='Main gate')
    is_supervisor = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @property
    def access_status(self):
        if self.revoked_at:
            return 'Revoked'
        if self.accepted_at:
            return 'Accepted'
        return 'Expired' if self.expires_at <= timezone.now() else 'Pending'


class AccessAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    subject = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    detail = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
