"""Private poster import: local OCR, palette extraction and review-only suggestions."""
import colorsys
import csv
from datetime import datetime
import io
import os
import re
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.core.ratelimit import ratelimit
from apps.events.palettes import hex_rgb, poster_palette
from .permissions import seller_required

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000


def load_poster(upload):
    if not upload or upload.size > MAX_BYTES:
        raise ValueError('Choose a JPG, PNG or WebP poster up to 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            image = Image.open(upload)
            if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > MAX_PIXELS:
                raise ValueError('Choose a JPG, PNG or WebP poster under 20 megapixels.')
            image = ImageOps.exif_transpose(image)
            image.thumbnail((2400, 2400))
            # Match transparent artwork against a neutral dark canvas, not arbitrary hidden RGB.
            if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                rgba = image.convert('RGBA')
                canvas = Image.new('RGBA', rgba.size, '#101522')
                canvas.alpha_composite(rgba)
                return canvas.convert('RGB')
            return image.convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('We could not read this image. Try a JPG, PNG or WebP poster.') from exc


def extract_colours(image):
    small = image.copy()
    small.thumbnail((180, 180))
    quantized = small.quantize(colors=10)
    palette = quantized.getpalette()
    ranked = sorted(quantized.getcolors(), reverse=True)
    colours = []
    for count, index in ranked:
        colour = tuple(palette[index*3:index*3+3])
        if all(sum((a-b)**2 for a,b in zip(colour, previous)) > 35**2 for previous in colours):
            colours.append(colour)
    chromatic = [c for c in colours if colorsys.rgb_to_hsv(*(v/255 for v in c))[1] > .22 and max(c) > 55]
    vivid = [c for c in chromatic if max(c) > 100]
    primary = (vivid or chromatic or colours)[0]
    others = [c for c in (chromatic or colours) if c != primary]
    secondary = others[0] if others else primary
    return {'colours': [hex_rgb(c) for c in colours[:6]], 'accent': hex_rgb(primary),
            'secondary': hex_rgb(secondary), 'style': poster_palette(hex_rgb(primary), hex_rgb(secondary))}


def read_text(image):
    executable = shutil.which('tesseract')
    if not executable:
        return [], 'Text reading is unavailable right now. Your poster colours are ready.'
    try:
        with tempfile.TemporaryDirectory(prefix='serotix-poster-') as folder:
            path = Path(folder) / 'poster.png'
            image.save(path)
            result = subprocess.run(
                [executable, str(path), 'stdout', '-l', 'eng', '--psm', '11', 'tsv'],
                capture_output=True, text=True, timeout=15, check=True,
                env={**os.environ, 'OMP_THREAD_LIMIT': '1'},
            )
        lines = {}
        for row in csv.DictReader(io.StringIO(result.stdout), delimiter='\t'):
            text = (row.get('text') or '').strip()
            if row.get('level') != '5' or not text or float(row['conf']) < 35:
                continue
            key = (row['block_num'], row['par_num'], row['line_num'])
            group = lines.setdefault(key, {'words': [], 'height': 0, 'top': int(row['top'])})
            group['words'].append(text)
            group['height'] = max(group['height'], int(row['height']))
        return [{'text':' '.join(line['words'])[:500], 'height':line['height'], 'top':line['top']}
                for line in sorted(lines.values(), key=lambda item:item['top'])][:100], ''
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        return [], 'Text reading did not finish. Your colours are ready; try a clearer poster for text.'


def suggestions(lines):
    text = '\n'.join(line['text'] for line in lines)[:10000]
    fields = {}
    prefixes = {'title':r'(?:event|title)', 'venue':r'(?:venue|location)',
                'city':r'city', 'organizer_name':r'(?:organizer|organiser|presented by|hosted by)'}
    for field, prefix in prefixes.items():
        match = re.search(rf'(?im)^\s*{prefix}\s*[:–-]\s*(.+)$', text)
        if match:
            fields[field] = match.group(1).strip()[:{'title':200,'venue':200,'city':100,'organizer_name':150}[field]]
    if 'title' not in fields:
        candidates = [line for line in lines if len(line['text']) >= 4 and not re.search(
            r'(?i)\b(?:tickets?|venue|location|presents?|date|time|sponsored|early bird|vip|regular|kes|ksh|am|pm)\b|https?://|\d{3,}', line['text'])]
        if candidates:
            fields['title'] = max(candidates, key=lambda line:(line['height'], -line['top']))['text'][:200]
    month = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    date_match = re.search(rf'(?i)\b(?:\d{{1,2}}\s+{month}\s+\d{{4}}|{month}\s+\d{{1,2}},?\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})\b', text)
    time_match = re.search(r'(?i)\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text)
    if not time_match:
        time_match = re.search(r'(?i)\b(?:time|doors|starts?)\s*[:–-]?\s*([01]?\d|2[0-3]):([0-5]\d)\b', text)
    if date_match and time_match:
        raw = date_match.group(0).replace(',', '')
        date = None
        for fmt in ['%d %B %Y','%d %b %Y','%B %d %Y','%b %d %Y','%Y-%m-%d']:
            try:
                date = datetime.strptime(raw, fmt)
                break
            except ValueError:
                pass
        hour, minute = int(time_match.group(1)), int(time_match.group(2) or 0)
        meridiem = time_match.group(3).lower() if time_match.lastindex == 3 else None
        valid_hour = 1 <= hour <= 12 if meridiem else 0 <= hour <= 23
        if meridiem:
            hour = hour % 12 + (12 if meridiem == 'pm' else 0)
        if date and valid_hour and minute < 60:
            fields['start_at'] = date.replace(hour=hour, minute=minute).strftime('%Y-%m-%dT%H:%M')
    prices = list(dict.fromkeys(re.findall(r'(?i)\b(?:KES|KSHS?\.?)\s*[\d,]+(?:\.\d{1,2})?', text)))[:8]
    return {'text':text, 'fields':fields, 'prices':prices}


@seller_required
@require_POST
@never_cache
@ratelimit(key_prefix='poster-import', limit=8, window_seconds=600)
def analyse(request):
    if not cache.add('poster-import-worker', True, timeout=30):
        return JsonResponse({'error':'Another poster is being read. Please try again in a few moments.'}, status=429)
    try:
        try:
            image = load_poster(request.FILES.get('poster'))
        except ValueError as exc:
            return JsonResponse({'error':str(exc)}, status=400)
        colours = extract_colours(image)
        lines, warning = read_text(image)
        result = suggestions(lines)
        return JsonResponse({**result, 'palette':colours, 'warning':warning,
            'review_note':'Review every suggestion. Dates are interpreted as Nairobi time. Prices are reference only; set ticket tiers separately.'})
    finally:
        cache.delete('poster-import-worker')
