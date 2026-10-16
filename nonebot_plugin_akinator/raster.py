"""Local image cards for hosts whose browser renderer is busy or unavailable."""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import re

from .visual import answers, footer_text, genie_bytes, palette, theme_blocks


@lru_cache(maxsize=1)
def font_path():
    # Use CJK fonts rather than silently replacing Chinese with missing glyphs.
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"),
    )
    for name in candidates:
        if Path(name).is_file():
            return name
    raise RuntimeError("Local Akinator cards require a CJK font (Noto Sans CJK or WenQuanYi)")


def wrapped_lines(text, font, width):
    lines = []
    for paragraph in str(text).split("\n"):
        line = ""
        for char in paragraph:
            if line and font.getlength(line + char) > width:
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
    return lines


def render_png(state, *, photo=None, theme=None):
    from PIL import Image, ImageDraw, ImageFont

    theme = theme or {}
    colors = palette(theme)
    bg, panel, ink, muted, surface, tint, border, accent = (colors[key] for key in (
        "background-color", "card-background-color", "font-color-main", "font-color-sub",
        "surface-muted", "surface-accent", "border-color", "accent-color"))
    radius_match = re.search(r'--menu-radius:\s*(\d+)px', theme_blocks(theme))
    radius = min(30, max(6, int(radius_match[1]))) if radius_match else 22
    fonts = {size: ImageFont.truetype(font_path(), size) for size in (16, 17, 18, 19, 20, 21, 28)}
    guess = state.guess
    heading = guess.name if guess else state.question
    title_lines = wrapped_lines(heading, fonts[28], 416)
    description = wrapped_lines(guess.description, fonts[20], 416) if guess and guess.description else []
    portrait = None
    if guess and photo:
        try:
            with Image.open(BytesIO(photo[1])) as source:
                if source.width * source.height <= 20_000_000:
                    source.thumbnail((416, 240))
                    portrait = source.convert("RGBA")
        except Exception:
            # A broken optional portrait must not suppress the question card.
            pass
    footer_lines = wrapped_lines(footer_text(state), fonts[17], 788)
    bubble_height = 78 + len(title_lines) * 42
    if description:
        bubble_height += len(description) * 32 + 12
    y = 112 + bubble_height
    if portrait:
        y += portrait.height + 20
    credit_lines = wrapped_lines("图片提供：" + guess.pseudo, fonts[16], 464) if portrait and guess.pseudo else []
    if credit_lines:
        y += len(credit_lines) * 26 + 12
    controls_y = y + 20
    options = answers(state)
    stage_bottom = max(652, controls_y + len(options) * 64 - 10)
    footer_y = stage_bottom + 48
    height = footer_y + len(footer_lines) * 26 + 52
    image = Image.new("RGB", (900, height), bg)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 28, 872, height - 28), radius=radius, fill=panel, outline=border, width=1)
    draw.text((56, 56), "AKINATOR · 网络天才", font=fonts[18], fill=accent)
    motto = "想好一个人物，让我来猜"
    draw.text((844 - fonts[16].getlength(motto), 57), motto, font=fonts[16], fill=muted)
    genie = genie_bytes(state)
    if genie:
        with Image.open(BytesIO(genie)) as source:
            source = source.convert("RGBA")
            source.thumbnail((300, 530))
            image.paste(source, (56 + (300 - source.width) // 2,
                                112 + (stage_bottom - 112 - source.height) // 2), source)
    draw.rounded_rectangle((380, 112, 844, 112 + bubble_height), radius=radius,
                           fill=surface, outline=border, width=1)
    draw.polygon(((366, 178), (381, 162), (381, 194)), fill=surface)
    draw.line(((380, 162), (366, 178), (380, 194)), fill=border, width=1)
    draw.text((404, 132), "我猜，你想的是……" if guess else f"第 {state.question_number} 个问题",
              font=fonts[17], fill=accent)
    y = 166
    for line in title_lines:
        draw.text((404, y), line, font=fonts[28], fill=ink)
        y += 42
    if description:
        for line in description:
            draw.text((404, y + 12), line, font=fonts[20], fill=ink)
            y += 32
    y = 112 + bubble_height + 20
    if portrait:
        image.paste(portrait, (380 + (464 - portrait.width) // 2, y), portrait)
        y += portrait.height + 20
    for line in credit_lines:
        draw.text((380, y), line, font=fonts[16], fill=muted)
        y += 26
    for i, (number, label, key) in enumerate(options):
        y = controls_y + i * 64
        draw.rounded_rectangle((380, y, 844, y + 54), radius=12, fill=panel, outline=border, width=1)
        draw.rounded_rectangle((396, y + 11, 428, y + 43), radius=9, fill=tint)
        draw.text((412, y + 27), number, font=fonts[19], fill=accent, anchor="mm")
        draw.text((442, y + 12), label, font=fonts[21], fill=ink)
        draw.text((828 - fonts[16].getlength(key), y + 16), key, font=fonts[16], fill=muted)
    draw.line((56, footer_y - 24, 844, footer_y - 24), fill=border, width=1)
    for i, line in enumerate(footer_lines):
        draw.text((56, footer_y + i * 26), line, font=fonts[17], fill=muted)
    image = image.resize((1350, round(height * 1.5)), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
