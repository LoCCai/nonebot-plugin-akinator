"""Local image cards for hosts whose browser renderer is busy or unavailable."""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import re


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
    dark = theme.get("palette_mode") == "night"
    bg, panel, ink, muted = (
        ("#121827", "#1d2537", "#f2f4ff", "#adb6d0") if dark else
        ("#f1edf9", "#ffffff", "#28243d", "#6d6880")
    )
    raw_accent = str(theme.get("accent_rgb", "130,85,220"))
    accent = tuple(map(int, raw_accent.split(","))) if re.fullmatch(
        r"\d{1,3},\s*\d{1,3},\s*\d{1,3}", raw_accent
    ) else (130, 85, 220)
    if any(value > 255 for value in accent):
        accent = (130, 85, 220)
    panel_rgb = tuple(int(panel[i:i + 2], 16) for i in (1, 3, 5))
    tint = tuple(round(a * .10 + b * .90) for a, b in zip(accent, panel_rgb))
    fonts = {size: ImageFont.truetype(font_path(), size) for size in (17, 18, 19, 21, 22, 32)}
    guess = state.guess
    heading = guess.name if guess else state.question
    title_lines = wrapped_lines(heading, fonts[32], 704)
    description = wrapped_lines(guess.description, fonts[22], 704) if guess and guess.description else []
    portrait = None
    if guess and photo:
        try:
            with Image.open(BytesIO(photo[1])) as source:
                if source.width * source.height <= 20_000_000:
                    source.thumbnail((500, 300))
                    portrait = source.convert("RGBA")
        except Exception:
            # A broken optional portrait must not suppress the question card.
            pass
    footer = "回复文字或序号即可 · " + ("上一题 / B · " if state.answer_depth else "") + "退出 / E"
    footer_lines = wrapped_lines(footer, fonts[17], 704)
    y = 150 + len(title_lines) * 48 + 18
    if description:
        y += len(description) * 34 + 18
    if portrait:
        y += portrait.height + 20
    credit_lines = wrapped_lines("图片提供：" + guess.pseudo, fonts[17], 704) if portrait and guess.pseudo else []
    if credit_lines:
        y += len(credit_lines) * 26 + 12
    controls_y = y
    footer_y = controls_y + (58 if guess else 128) + 26
    height = footer_y + len(footer_lines) * 26 + 58
    image = Image.new("RGB", (820, height), bg)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, 796, height - 24), radius=24, fill=panel, outline=tint, width=2)
    draw.text((58, 58), "AKINATOR · 网络天才", font=fonts[18], fill=accent)
    draw.text((58, 110), "我猜，你想的是……" if guess else f"第 {state.question_number} 个问题",
              font=fonts[19], fill=muted)
    y = 150
    for line in title_lines:
        draw.text((58, y), line, font=fonts[32], fill=ink)
        y += 48
    y += 18
    if description:
        for line in description:
            draw.text((58, y), line, font=fonts[22], fill=ink)
            y += 34
        y += 18
    if portrait:
        image.paste(portrait, ((820 - portrait.width) // 2, y), portrait)
        y += portrait.height + 20
    for line in credit_lines:
        draw.text((58, y), line, font=fonts[17], fill=muted)
        y += 26
    options = ("猜对了？回复「是」", "猜错了？回复「否」或「继续」") if guess else (
        "1   是", "2   否", "3   不知道", "4   可能是", "5   可能不是"
    )
    x, y = 58, controls_y
    for label in options:
        width = int(fonts[21].getlength(label)) + 36 if guess else 226
        if x + width > 762:
            x, y = 58, y + 70
        draw.rounded_rectangle((x, y, x + width, y + 58), radius=12, fill=tint)
        draw.text((x + 18, y + 13), label, font=fonts[21], fill=ink)
        x += width + 12
    for i, line in enumerate(footer_lines):
        draw.text((58, footer_y + i * 26), line, font=fonts[17], fill=muted)
    image = image.resize((1230, round(height * 1.5)), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
