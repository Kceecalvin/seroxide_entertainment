"""Bounded poster colours shared by saved themes and the import preview."""
import re


def safe_hex(value, fallback='#e6ba70'):
    return value.lower() if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else fallback


def rgb(value):
    value = safe_hex(value)
    return tuple(int(value[i:i+2], 16) for i in (1, 3, 5))


def hex_rgb(channels):
    return '#' + ''.join(f'{max(0, min(255, round(c))):02x}' for c in channels)


def luminance(channels):
    linear = [c / 255 / 12.92 if c / 255 <= .04045 else ((c / 255 + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))


def poster_palette(accent, secondary):
    source = rgb(accent)
    # Preserve hue while lightening the readable foreground colour as needed.
    readable = source
    for step in range(21):
        readable = tuple(c + (255-c) * step / 20 for c in source)
        if (luminance(readable) + .05) / (luminance((16, 21, 34)) + .05) >= 5:
            break
    return {
        '--event-accent': hex_rgb(readable),
        '--event-base': hex_rgb(c * .13 + 6 for c in source),
        '--event-glow': safe_hex(accent),
        '--event-secondary': safe_hex(secondary, '#255bea'),
        '--event-ink': '#101522',
    }


def poster_style(accent, secondary):
    return ';'.join(f'{key}:{value}' for key, value in poster_palette(accent, secondary).items())
