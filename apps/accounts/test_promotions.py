from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import AccountProfile, AccessAudit
from apps.accounts.promotions import caption_for
from apps.core.models import EmailDelivery
from apps.events.models import Event, PromotionRequest


class PromotionTests(TestCase):
    def setUp(self):
        cache.clear()
        User=get_user_model()
        self.owner=User.objects.create_user('promo-owner',email='owner@example.test',password='Test123456!')
        self.other=User.objects.create_user('promo-other',password='Test123456!')
        self.admin=User.objects.create_user('promo-admin',password='Test123456!')
        for user,role in [(self.owner,'seller'),(self.other,'seller'),(self.admin,'admin')]:AccountProfile.objects.create(user=user,role=role)
        self.event=Event.objects.create(owner=self.owner,title='Promotion event',description='A concert',venue='Hall',city='Nairobi',start_at=timezone.now()+timedelta(days=10),review_status='draft',is_published=False)
        self.url=reverse('accounts:seller_promote',args=[self.event.pk])
        self.client.force_login(self.owner)

    def data(self):
        response=self.client.get(self.url)
        return {'platforms':['instagram','serotix'],'audience':'Nairobi music fans','budget':'5000','email':'owner@example.test','notes':'Please quote a launch campaign.','submission_token':response.context['form']['submission_token'].value()}

    def test_enquiry_is_saved_once_and_notifies_support_once(self):
        data=self.data()
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        self.assertEqual(self.client.post(self.url,data).status_code,302)
        self.assertEqual(PromotionRequest.objects.count(),1)
        self.assertEqual(EmailDelivery.objects.count(),1)
        row=PromotionRequest.objects.get()
        self.assertEqual(row.organizer,self.owner)
        self.assertEqual(row.platforms,['instagram','serotix'])
        self.assertEqual(row.status,'new')
        self.assertContains(self.client.get(self.url),'Offer requested')

    def test_cross_client_access_and_forged_submission_are_rejected(self):
        data=self.data()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.post(self.url,data).status_code,404)
        other_event=Event.objects.create(owner=self.other,title='Other client',venue='Hall',start_at=timezone.now()+timedelta(days=10))
        response=self.client.post(reverse('accounts:seller_promote',args=[other_event.pk]),data)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'This form has expired')
        self.assertEqual(PromotionRequest.objects.count(),0)

    def test_invalid_platform_and_negative_budget_do_not_create_request(self):
        data=self.data();data['platforms']=['not-a-platform'];data['budget']='-1'
        response=self.client.post(self.url,data)
        self.assertEqual(response.status_code,200)
        self.assertIn('platforms',response.context['form'].errors)
        self.assertIn('budget',response.context['form'].errors)
        self.assertFalse(PromotionRequest.objects.exists())

    def test_admin_can_follow_up_and_seller_cannot_update_status(self):
        self.client.post(self.url,self.data());enquiry=PromotionRequest.objects.get()
        status_url=reverse('dashboard:promotion_update',args=[enquiry.pk])
        self.assertEqual(self.client.post(status_url,{'status':'closed'}).status_code,403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('dashboard:promotions')),self.event.title)
        self.assertEqual(self.client.get(status_url).status_code,405)
        self.assertEqual(self.client.post(status_url,{'status':'unknown'}).status_code,400)
        self.assertEqual(self.client.post(status_url,{'status':'contacted'}).status_code,302)
        enquiry.refresh_from_db();self.assertEqual(enquiry.status,'contacted');self.assertEqual(enquiry.updated_by,self.admin)
        self.assertTrue(AccessAudit.objects.filter(actor=self.admin,subject=self.owner).exists())

    def test_draft_and_closed_checkout_captions_do_not_claim_tickets_are_on_sale(self):
        self.assertNotIn(self.event.get_absolute_url(),caption_for(self.event))
        self.event.review_status='approved';self.event.is_published=True;self.event.save()
        with patch('apps.payments.availability.available_methods',return_value=[]):
            self.assertIn('booking opens soon',caption_for(self.event))
            self.assertNotIn('Book your spot',caption_for(self.event))
        self.event.start_at=timezone.now()-timedelta(days=1)
        self.assertIn('Thank you',caption_for(self.event))
        self.assertNotIn('Coming soon',caption_for(self.event))

    def test_advert_export_never_includes_a_private_draft_link_or_qr(self):
        data=self.client.get(self.url).context['advert_data']
        self.assertEqual(data['url'],'')
        self.assertEqual(data['qr'],'')
        self.event.review_status='approved';self.event.is_published=True;self.event.save()
        data=self.client.get(self.url).context['advert_data']
        self.assertTrue(data['url'].endswith(self.event.get_absolute_url()))
        self.assertTrue(data['qr'].startswith('data:image/png;base64,'))
