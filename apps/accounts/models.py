from django.conf import settings
from django.db import models


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

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'event'], name='unique_event_scanner')]


class AccessAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    subject = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    detail = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
