"""Poster-led promotional previews and event-scoped requests for a quote."""
from uuid import uuid4
import base64
import io
import qrcode

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.models import AccessAudit
from apps.core.mailer import queue_email
from apps.core.ratelimit import ratelimit
from apps.events.models import Event, PromotionRequest
from .permissions import seller_required, admin_required

PLATFORMS = [('instagram','Instagram'),('facebook','Facebook'),('tiktok','TikTok'),('serotix','SeroTix placement')]
SALT = 'event-promotion-request'


class PromotionForm(forms.Form):
    platforms = forms.MultipleChoiceField(choices=PLATFORMS, widget=forms.CheckboxSelectMultiple, label='Where would you like to promote?')
    audience = forms.CharField(max_length=200, label='Who are you trying to reach?', widget=forms.TextInput(attrs={'placeholder':'e.g. Nairobi music fans, ages 21–35'}))
    budget = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2, label='Budget guide (KES)', help_text='Optional. This helps the team tailor an offer; it is not a charge.')
    email = forms.EmailField(label='Where should we send your offer?')
    notes = forms.CharField(required=False, max_length=2000, label='Anything else?', widget=forms.Textarea(attrs={'rows':3,'placeholder':'Your goals, preferred dates, or a ticket offer you want to promote.'}))
    submission_token = forms.CharField(widget=forms.HiddenInput, max_length=500)


def caption_for(event):
    when = timezone.localtime(event.start_at).strftime('%d %B %Y · %I:%M %p EAT')
    price = event.min_price
    parts = [event.title, f'{when}\n{event.venue}, {event.city}']
    if price is not None and not event.is_past and not event.is_sold_out:
        parts.append(f'Tickets from KES {price:,.2f}')
    if event.is_past:
        parts.append('An event to remember. Thank you for being part of it.')
    elif event.is_published:
        from apps.payments.availability import available_methods
        parts.append('Currently sold out. Check the event page for updates:' if event.is_sold_out else 'Book your spot:' if available_methods() else 'Event details — online booking opens soon:')
        parts.append(f'https://{settings.SITE_DOMAIN}{event.get_absolute_url()}')
    else:
        parts.append('Coming soon. Booking link available after publication.')
    return '\n\n'.join(parts)


def advert_qr(event):
    if not event.is_published:
        return ''
    output = io.BytesIO()
    qr = qrcode.QRCode(box_size=4, border=4)
    qr.add_data(f'https://{settings.SITE_DOMAIN}{event.get_absolute_url()}')
    qr.make(fit=True)
    qr.make_image(fill_color='black', back_color='white').save(output, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')


@seller_required
@never_cache
@ratelimit(key_prefix='promotion-workspace', limit=30, window_seconds=600)
def workspace(request, pk):
    event = get_object_or_404(Event.objects.prefetch_related('ticket_types'), pk=pk, owner=request.user)
    token = signing.dumps({'user':request.user.pk, 'event':event.pk, 'nonce':str(uuid4())}, salt=SALT)
    form = PromotionForm(request.POST or None, initial={'email':request.user.email,'audience':event.city,'submission_token':token})
    if request.method == 'POST' and form.is_valid():
        try:
            signed = signing.loads(form.cleaned_data['submission_token'], salt=SALT, max_age=7200)
            if signed['user'] != request.user.pk or signed['event'] != event.pk:
                raise signing.BadSignature
        except (signing.BadSignature, KeyError, TypeError):
            form.add_error(None, 'This form has expired. Reload this page and try again.')
        else:
            with transaction.atomic():
                # Match the same event-first lock order as organizer/gate management.
                get_object_or_404(Event.objects.select_for_update(), pk=pk, owner=request.user)
                enquiry, created = PromotionRequest.objects.get_or_create(
                    submission_id=signed['nonce'], defaults={
                        'event':event,'organizer':request.user,'platforms':form.cleaned_data['platforms'],
                        'email':form.cleaned_data['email'],'budget':form.cleaned_data['budget'],
                        'audience':form.cleaned_data['audience'],'notes':form.cleaned_data['notes'],
                    })
                if created:
                    body = (f'Promotion enquiry #{enquiry.pk}\nEvent: {event.title}\nOrganizer: {request.user.get_username()}\n'
                            f'Reply to: {enquiry.email}\nPlatforms: {enquiry.platform_labels}\n'
                            f'Budget guide: {enquiry.budget if enquiry.budget is not None else "Not provided"} KES\n'
                            f'Audience: {enquiry.audience}\nNotes: {enquiry.notes}\n'
                            f'Review: https://{settings.SITE_DOMAIN}{reverse("dashboard:promotions")}')
                    context={'heading':'New event promotion enquiry','message':body,
                        'action_url':f'https://{settings.SITE_DOMAIN}{reverse("dashboard:promotions")}',
                        'site_name':settings.SITE_NAME,'site_domain':settings.SITE_DOMAIN,'scheme':'https',
                        'support_phone':settings.SITE_SUPPORT_PHONE,'support_phone_tel':settings.SITE_SUPPORT_PHONE_TEL,
                        'support_email':settings.SITE_SUPPORT_EMAIL}
                    queue_email(recipient=settings.SITE_SUPPORT_EMAIL,subject=f'Promotion enquiry #{enquiry.pk}: {event.title}',
                        text=body,html=render_to_string('emails/account_notice.html',context),
                        payload={'reply_to':enquiry.email},key=f'promotion-enquiry:{enquiry.pk}')
            messages.success(request, 'Your promotion enquiry is saved. The team will follow up with an offer. No campaign has been booked or charged.')
            return redirect('accounts:seller_promote', pk=pk)
    return render(request, 'seller/promote.html', {
        'event':event,'form':form,'caption':caption_for(event),
        'advert_data':{'title':event.title,'organizer':event.organizer_name,'venue':f'{event.venue}, {event.city}',
            'date':timezone.localtime(event.start_at).strftime('%d %B %Y · %I:%M %p EAT'),
            'category':event.get_category_display(),
            'cta':'Event recap' if event.is_past else 'Explore the event' if event.is_published else 'Coming soon',
            'url':f'https://{settings.SITE_DOMAIN}{event.get_absolute_url()}' if event.is_published else '',
            'qr':advert_qr(event), 'slug':event.slug},
        'enquiries':event.promotion_requests.filter(organizer=request.user)[:10],
    })


@admin_required
@never_cache
def enquiries(request):
    status=request.GET.get('status','new')
    rows=PromotionRequest.objects.select_related('event','organizer','updated_by')
    if status in PromotionRequest.Status.values:
        rows=rows.filter(status=status)
    else:
        status='all'
    return render(request, 'dashboard/promotions.html', {'enquiries':Paginator(rows,20).get_page(request.GET.get('page')),
        'selected_status':status,'status_options':PromotionRequest.Status.choices})


@admin_required
@require_POST
@transaction.atomic
def update_status(request, pk):
    enquiry=get_object_or_404(PromotionRequest.objects.select_for_update(),pk=pk)
    status=request.POST.get('status')
    if status not in PromotionRequest.Status.values:
        return HttpResponseBadRequest('Choose a valid enquiry status.')
    previous=enquiry.status
    enquiry.status=status;enquiry.updated_by=request.user;enquiry.save(update_fields=['status','updated_by','updated_at'])
    AccessAudit.objects.create(actor=request.user,subject=enquiry.organizer,detail=f'Promotion enquiry {enquiry.pk}: {previous} → {status}')
    messages.success(request,'Promotion enquiry updated.')
    return redirect('dashboard:promotions')
