"""Shared artwork and theme tokens for browser and local Akinator cards."""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import re

from .const import DATA_AKITUDE_DIR


def theme_blocks(theme):
    # Reuse the host palette without importing its unrelated page selectors,
    # remote fonts or illustrations into a self-contained game card.
    return "\n".join(re.findall(r':root\[data-theme="(?:light|dark)"\]\s*\{[^}]+\}',
                                str(theme.get("theme_css", ""))))


def palette(theme):
    mode = theme.get("theme", theme.get("palette_mode", "day"))
    dark = theme.get("palette_mode", mode) == "night"
    colors = dict(zip(("background-color", "card-background-color", "font-color-main", "font-color-sub",
                       "surface-muted", "surface-accent", "border-color", "accent-color"),
                      ("#121827", "#1d2537", "#f2f4ff", "#adb6d0", "#242d43", "#33324f", "#414b64", "#cbb0ff") if dark else
                      ("#f1edf9", "#ffffff", "#28243d", "#6d6880", "#f8f5fc", "#ede5f8", "#ddd5ea", "#8255dc")))
    block = re.search(r':root\[data-theme="' + ('dark' if mode == 'night' else 'light') + r'"\]\s*\{([^}]+)',
                      theme_blocks(theme))
    if block:
        for key, value in re.findall(r'--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*[;}]', block[1] + '}'):
            colors[key] = value
    elif re.fullmatch(r'\d{1,3},\s*\d{1,3},\s*\d{1,3}', str(theme.get("accent_rgb", ""))):
        rgb = tuple(map(int, theme["accent_rgb"].split(',')))
        if all(value <= 255 for value in rgb):
            colors['accent-color'] = '#%02x%02x%02x' % rgb
    return colors


@lru_cache(maxsize=24)
def _read_genie(path, mtime):
    data = path.read_bytes()
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            # Official sprites have large transparent margins; crop them so the
            # visible genie fills the left column rather than shrinking away.
            image = image.convert("RGBA")
            bounds = image.getbbox()
            if bounds:
                output = BytesIO()
                image.crop(bounds).save(output, format="PNG")
                return output.getvalue()
    except ImportError:
        pass
    return data


def genie_name(state):
    filename = "confiant.png" if state.guess else str(state.akitude)
    if not re.fullmatch(r'[a-z_]+\.png', filename):
        filename = "defi.png"
    return filename


def genie_bytes(state):
    filename = genie_name(state)
    for name in dict.fromkeys((filename, "defi.png")):
        path = DATA_AKITUDE_DIR / name
        if path.is_file() and 0 < path.stat().st_size < 3_000_000:
            try:
                return _read_genie(path, path.stat().st_mtime_ns)
            except (OSError, ValueError):
                continue
    return None


def footer_text(state):
    return "回复序号或文字即可 · " + ("上一题 / B · " if state.answer_depth else "") + "退出 / E"


def answers(state):
    if state.guess:
        return (("是", "猜对了", "Y"), ("否", "猜错了，继续猜", "N / 继续"))
    return tuple((str(i), label, key) for i, (label, key) in enumerate(
        (("是", "Y"), ("否", "N"), ("不知道", "IDK"), ("可能是", "P"), ("可能不是", "PN")), 1))
