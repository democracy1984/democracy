"""Рендер карточек статистики на PIL: шрифты, эмодзи, текст, GIF.

Вынесено из main.py целиком, логика не менялась.
"""

import io
import os
import re
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from config import GIF_FRAME_STEP

EMOJI_RE = re.compile(
    r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u20E3]'
)

# Кэш уже нарезанных кадров фона: ключ (путь, mtime, размер, шаг)
_GIF_STRIP_CACHE = {}


def find_font(name):
    import subprocess
    candidates = [
        f'/usr/share/fonts/truetype/dejavu/{name}',
        f'/usr/share/fonts/dejavu/{name}',
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    try:
        matched = subprocess.run(
            ['fc-match', '-f', '%{file}', name],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if matched and os.path.exists(matched):
            return matched
    except Exception:
        pass
    return candidates[0]


def find_emoji_font():
    candidates = [
        '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
        '/usr/share/fonts/noto/NotoColorEmoji.ttf',
        os.path.expanduser('~/.local/share/fonts/NotoColorEmoji.ttf'),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    try:
        matched = subprocess.run(
            ['fc-match', '-f', '%{file}', 'Noto Color Emoji'],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if matched and os.path.exists(matched):
            return matched
    except Exception:
        pass
    return None


def split_text_runs(text, font, emoji_font):
    """Разбивает текст на (часть, шрифт): обычный шрифт + эмодзи."""
    if not emoji_font:
        return [(text, font)]
    runs = []
    pos = 0
    for m in EMOJI_RE.finditer(text):
        if m.start() > pos:
            runs.append((text[pos:m.start()], font))
        runs.append((m.group(0), emoji_font))
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], font))
    return runs


def text_runs_width(text, font, emoji_font):
    return sum(f.getlength(part) for part, f in split_text_runs(text, font, emoji_font))


def draw_text_runs(draw, xy, text, font, emoji_font, fill):
    x, y = xy
    for part, f in split_text_runs(text, font, emoji_font):
        draw.text((x, y), part, font=f, fill=fill)
        x += f.getlength(part)


def crop_cover(img, size):
    """Масштабирует изображение, полностью закрывая size, и обрезает по центру."""
    tw, th = size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return img.crop((left, top, left + tw, top + th))


def gif_strip_frames(path, strip_size, step=GIF_FRAME_STEP):
    """Возвращает обрезанные кадры фоновой гифки (каждый step-й), кэшируя результат."""
    key = (os.path.realpath(path), os.path.getmtime(path), strip_size, step)
    cached = _GIF_STRIP_CACHE.get(key)
    if cached is not None:
        return cached
    bg = Image.open(path)
    frame_count = getattr(bg, 'n_frames', 1)
    frames, durations = [], []
    for i in range(0, frame_count, step):
        bg.seek(i)
        frames.append(crop_cover(bg.convert('RGB'), strip_size))
        durations.append((bg.info.get('duration', 50) or 50) * step)
    _GIF_STRIP_CACHE[key] = (frames, durations)
    return frames, durations


def render_telegram_bubble(title, sections, strip_gif_path=None, strip_heading=None):
    """Рисует карточку в стиле прежнего HTML-шаблона без браузера.
    Если заданы strip_gif_path и strip_heading — вместо заголовка этой секции вставляется
    обрезанная по ширине анимированная гифка (карточка сохраняется как GIF), иначе — статичный PNG."""
    width, padding, line_height = 650, 24, 27
    strip_height = line_height + 18
    font = ImageFont.truetype(find_font('DejaVuSans.ttf'), 16)
    bold_font = ImageFont.truetype(find_font('DejaVuSans-Bold.ttf'), 17)
    emoji_font = None
    emoji_path = find_emoji_font()
    if emoji_path:
        try:
            emoji_font = ImageFont.truetype(emoji_path, 16, embedded_color=True)
        except Exception:
            emoji_font = None
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    max_width = width - padding * 2 - 28

    def wrap(text):
        lines, line = [], ''
        for word in text.split() or ['']:
            candidate = f'{line} {word}'.strip()
            if line and text_runs_width(candidate, font, emoji_font) > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        return lines + [line]

    def is_strip(heading):
        return (strip_heading and strip_gif_path and os.path.exists(strip_gif_path)
                and heading == strip_heading)

    prepared_sections = []
    for heading, values in sections:
        lines = []
        for value in values:
            lines.extend(wrap(value))
        prepared_sections.append((heading, lines or ['Нет данных']))

    section_height = sum(
        (strip_height if is_strip(heading) else line_height) + 20 + len(lines) * line_height + 20
        for heading, lines in prepared_sections
    )
    card_size = (width, padding * 2 + line_height * 2 + section_height + 8)

    def draw_card(image, strip_frame=None):
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, width - 8, image.height - 8), radius=24, fill='#182533')
        y = padding
        draw_text_runs(draw, (padding, y), title, bold_font, emoji_font, '#6ab0f3')
        y += line_height + 8
        strip_y = None
        for heading, lines in prepared_sections:
            if is_strip(heading):
                if strip_frame is not None:
                    overlay = Image.new('RGBA', strip_frame.size, (0, 0, 0, 110))
                    composed = Image.alpha_composite(strip_frame.convert('RGBA'), overlay).convert('RGB')
                    image.paste(composed, (padding, y))
                strip_y = y
                draw_text_runs(draw, (padding + 14, y + 13), heading, bold_font, emoji_font, '#ffffff')
                y += strip_height
            else:
                draw_text_runs(draw, (padding, y), heading, bold_font, emoji_font, '#ffffff')
                y += line_height
            quote_bottom = y + 12 + len(lines) * line_height + 8
            draw.rounded_rectangle((padding, y, width - padding, quote_bottom), radius=10, fill='#101921')
            draw.rectangle((padding, y + 8, padding + 3, quote_bottom - 8), fill='#6ab0f3')
            for line in lines:
                draw_text_runs(draw, (padding + 14, y + 8), line, font, emoji_font, '#f5f5f5')
                y += line_height
            y = quote_bottom + 20

        timestamp = datetime.now().strftime('%H:%M')
        time_width = text_runs_width(timestamp, font, emoji_font)
        draw.text((width - padding - time_width, image.height - padding - 4), timestamp, font=font, fill='#7f91a4')
        return image, strip_y

    output = io.BytesIO()

    if any(is_strip(heading) for heading, _ in prepared_sections):
        try:
            strip_size = (width - padding * 2, strip_height)
            frames, durations = gif_strip_frames(strip_gif_path, strip_size, GIF_FRAME_STEP)
            base, strip_y = draw_card(Image.new('RGB', card_size, '#0e1621'))
            overlay = Image.new('RGBA', strip_size, (0, 0, 0, 110))
            out_frames = []
            for strip_frame in frames:
                frame = base.copy()
                composed = Image.alpha_composite(strip_frame.convert('RGBA'), overlay).convert('RGB')
                frame.paste(composed, (padding, strip_y))
                draw_text_runs(ImageDraw.Draw(frame), (padding + 14, strip_y + 13),
                               strip_heading, bold_font, emoji_font, '#ffffff')
                out_frames.append(frame)
            # Единая палитра из нескольких кадров: без мерцания цветов
            sample = max(1, min(6, len(out_frames)))
            palette = out_frames[::len(out_frames) // sample][:sample]
            montage = Image.new('RGB', (card_size[0], card_size[1] * len(palette)))
            for j, f in enumerate(palette):
                montage.paste(f, (0, j * card_size[1]))
            shared_palette = montage.quantize(
                colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE,
            )
            quantized = [
                f.quantize(palette=shared_palette, dither=Image.Dither.NONE)
                for f in out_frames
            ]
            quantized[0].save(
                output, 'GIF', save_all=True, append_images=quantized[1:],
                loop=0, duration=durations,
            )
            output.name = 'stats.gif'
            output.seek(0)
            return output
        except Exception as e:
            print(f"[-] Ошибка рендера GIF со вставкой гифки: {e}")

    image, _ = draw_card(Image.new('RGB', card_size, '#0e1621'))
    image.save(output, 'PNG')
    output.name = 'stats.png'
    output.seek(0)
    return output
