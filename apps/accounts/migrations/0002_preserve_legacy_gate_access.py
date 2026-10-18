from django.conf import settings
from django.db import migrations


def preserve_gate_access(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Profile = apps.get_model('accounts', 'AccountProfile')
    Assignment = apps.get_model('accounts', 'GateAssignment')
    Event = apps.get_model('events', 'Event')
    # Existing is_staff-only users could scan every existing event. Preserve
    # that access during migration; future events require explicit assignment.
    event_ids = list(Event.objects.values_list('pk', flat=True))
    for user in User.objects.filter(is_staff=True, is_superuser=False):
        profile, created = Profile.objects.get_or_create(user_id=user.pk, defaults={'role': 'scanner'})
        if created:
            Assignment.objects.bulk_create([Assignment(user_id=user.pk, event_id=pk) for pk in event_ids], ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0001_initial')]
    operations = [migrations.RunPython(preserve_gate_access, migrations.RunPython.noop)]
