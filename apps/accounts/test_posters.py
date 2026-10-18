import io
import shutil
import subprocess
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, SimpleTestCase
from django.urls import reverse
from PIL import Image, ImageDraw, ImageFont
from apps.accounts.models import AccountProfile
from apps.accounts.posters import extract_colours, load_poster, read_text, suggestions
from apps.events.models import Event
from apps.events.palettes import luminance, poster_palette, poster_style, rgb


def poster_file():
    image=Image.new('RGB',(1200,1500),'#102a43')
    draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,1199,170),fill='#d78232')
    fontpath='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    if not __import__('pathlib').Path(fontpath).exists():
        fontpath='/usr/share/fonts/TTF/DejaVuSans.ttf'
    try: font=ImageFont.truetype(fontpath,44)
    except OSError: font=ImageFont.load_default(size=44)
    for i,line in enumerate(['EVENT: COASTAL RHYTHMS','VENUE: OCEAN GARDENS','CITY: KILIFI','DATE: 20 DECEMBER 2030','TIME: 7:00 PM','REGULAR KES 1500','ORGANIZER: COAST LIVE']):
        draw.text((65,230+i*120),line,font=font,fill='white')
    data=io.BytesIO();image.save(data,format='PNG')
    return SimpleUploadedFile('poster.png',data.getvalue(),content_type='image/png')


class PosterPaletteTests(SimpleTestCase):
    def test_import_retains_artwork_colours_and_readable_foreground(self):
        image=Image.new('RGB',(120,120),'#b52055')
        palette=extract_colours(image)
        self.assertEqual(palette['accent'],'#b52055')
        self.assertEqual(palette['style']['--event-glow'],'#b52055')
        contrast=(luminance(rgb(palette['style']['--event-accent']))+.05)/(luminance((16,21,34))+.05)
        self.assertGreaterEqual(contrast,4.5)
        self.assertNotIn('url',poster_style('red;url(evil)','#123456'))

    def test_invalid_files_and_formats_are_rejected(self):
        with self.assertRaises(ValueError):load_poster(SimpleUploadedFile('fake.png',b'<svg onload=alert(1)>'))
        with self.assertRaises(ValueError):load_poster(SimpleUploadedFile('large.png',b'x'*(5*1024*1024+1)))
        gif=io.BytesIO();Image.new('RGB',(20,20)).save(gif,format='GIF')
        with self.assertRaises(ValueError):load_poster(SimpleUploadedFile('poster.gif',gif.getvalue()))

    def test_full_dates_and_prices_are_suggestions_not_ticket_data(self):
        lines=[{'text':text,'height':20,'top':i*30} for i,text in enumerate(['EVENT: COASTAL RHYTHMS','VENUE: OCEAN GARDENS','CITY: KILIFI','20 December 2030','TIME: 7:00 PM','REGULAR KES 1500'])]
        result=suggestions(lines)
        self.assertEqual(result['fields']['title'],'COASTAL RHYTHMS')
        self.assertEqual(result['fields']['venue'],'OCEAN GARDENS')
        self.assertEqual(result['fields']['start_at'],'2030-12-20T19:00')
        self.assertEqual(result['prices'],['KES 1500'])
        self.assertNotIn('price',result['fields'])
        result=suggestions([{'text':'20/12 at 7 PM','height':30,'top':0}])
        self.assertNotIn('start_at',result['fields'])

    def test_missing_or_timed_out_ocr_still_allows_colour_import(self):
        image=Image.new('RGB',(20,20),'red')
        with patch('apps.accounts.posters.shutil.which',return_value=None):
            self.assertIn('unavailable',read_text(image)[1])
        with patch('apps.accounts.posters.shutil.which',return_value='/usr/bin/tesseract'),patch('apps.accounts.posters.subprocess.run',side_effect=subprocess.TimeoutExpired('tesseract',15)):
            self.assertIn('did not finish',read_text(image)[1])

    def test_real_ocr_reads_a_clear_poster(self):
        if not shutil.which('tesseract'):self.skipTest('Install Tesseract + English data for OCR integration verification.')
        lines,warning=read_text(load_poster(poster_file()))
        self.assertFalse(warning)
        result=suggestions(lines)
        self.assertEqual(result['fields']['title'],'COASTAL RHYTHMS')
        self.assertEqual(result['fields']['city'],'KILIFI')
        self.assertEqual(result['fields']['start_at'],'2030-12-20T19:00')


class PosterImportAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user=get_user_model().objects.create_user('poster-owner',password='Test123456!')
        self.profile=AccountProfile.objects.create(user=self.user,role='seller')
        self.url=reverse('accounts:poster_import')

    def test_import_is_private_post_only_and_requires_csrf(self):
        self.assertEqual(self.client.post(self.url).status_code,302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code,405)
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.user)
        self.assertEqual(secure.post(self.url,{'poster':poster_file()}).status_code,403)
        self.profile.role='buyer';self.profile.save()
        self.assertEqual(self.client.post(self.url,{'poster':poster_file()}).status_code,403)

    def test_analysis_does_not_create_events_and_preserves_no_store(self):
        self.client.force_login(self.user)
        with patch('apps.accounts.posters.read_text',return_value=([{'text':'EVENT: Sample','height':40,'top':0}],'')):
            response=self.client.post(self.url,{'poster':poster_file()})
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(response.json()['fields']['title'],'Sample')
        self.assertEqual(Event.objects.count(),0)
        self.assertIsNone(cache.get('poster-import-worker'))

    def test_invalid_and_busy_imports_are_safe_to_retry(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url).status_code,400)
        self.assertIsNone(cache.get('poster-import-worker'))
        cache.set('poster-import-worker',True,30)
        self.assertEqual(self.client.post(self.url,{'poster':poster_file()}).status_code,429)
        self.assertTrue(cache.get('poster-import-worker'))
