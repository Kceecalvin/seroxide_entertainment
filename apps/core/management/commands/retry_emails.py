from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from apps.core.models import EmailDelivery
from apps.core.mailer import deliver

class Command(BaseCommand):
    help = 'Retry a bounded batch of queued/failed transactional mail (up to five attempts).'

    def handle(self, *args, **options):
        eligible = Q(status__in=['pending', 'failed']) | Q(status='sending', updated_at__lt=timezone.now()-timedelta(minutes=10))
        ids = list(EmailDelivery.objects.filter(eligible, attempts__lt=5).order_by('created_at').values_list('pk', flat=True)[:100])
        sent = sum(deliver(pk) for pk in ids)
        self.stdout.write(f'Sent {sent} of {len(ids)} queued messages.')
