"""Self-contained cards; screenshots never wait for remote fonts or portraits."""
from __future__ import annotations

import asyncio
import base64
import html

from .const import DATA_ADDITIONAL_CSS_PATH, HTML_RENDER_AVAILABLE
from .integration import capture_html, theme_context
from .visual import answers, footer_text, genie_bytes, palette, theme_blocks


def card_html(state, *, photo=None, theme=None):
    theme = theme or {"palette_mode": "day"}
    dark = theme.get("theme", theme.get("palette_mode")) == "night"
    colors = palette(theme)
    defaults = ';'.join(f'--{key}:{value}' for key, value in colors.items())
    data = genie_bytes(state)
    genie = f'<img class="genie" alt="神灯天才" src="data:image/png;base64,{base64.b64encode(data).decode()}">' if data else ""
    if state.guess:
        title = "我猜，你想的是……"
        body = f'<h1>{html.escape(state.guess.name)}</h1><p class="description">{html.escape(state.guess.description)}</p>'
        portrait = ""
        if photo:
            mime, data = photo
            portrait = f'<img class="portrait" src="data:{mime};base64,{base64.b64encode(data).decode()}">'
        if state.guess.pseudo and photo:
            portrait += f'<p class="credit">图片提供：{html.escape(state.guess.pseudo)}</p>'
    else:
        title = f"第 {state.question_number} 个问题"
        body = f'<h1>{html.escape(state.question)}</h1>'
        portrait = ""
    controls = ''.join(f'<div class="option"><b>{number}</b><span>{label}</span><small>{key}</small></div>'
                       for number, label, key in answers(state))
    try:
        custom_css = DATA_ADDITIONAL_CSS_PATH.read_text("utf-8")
    except OSError:
        custom_css = ""
    return f'''<!doctype html><html data-theme="{'dark' if dark else 'light'}"><meta charset="utf-8"><style>
    :root{{{defaults};--menu-radius:22px;--background-image:none;--card-shadow:0 8px 28px #0000000c}}
    {theme_blocks(theme)}
    *{{box-sizing:border-box}}body{{margin:0;width:900px;padding:28px;background-color:var(--background-color);background-image:var(--background-image);color:var(--font-color-main);font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}}
    main{{background:var(--card-background-color);border-radius:var(--menu-radius);padding:28px;overflow:hidden;border:1px solid var(--border-color);box-shadow:var(--card-shadow)}}
    header{{display:flex;align-items:center;justify-content:space-between;padding-bottom:24px;color:var(--accent-color);font-weight:700;font-size:18px;letter-spacing:1px}}
    header span{{font-size:15px;font-weight:400;color:var(--font-color-sub)}}
    .stage{{display:grid;grid-template-columns:300px minmax(0,1fr);gap:24px;align-items:start}}
    .genie-panel{{min-height:540px;height:100%;display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse,color-mix(in srgb,var(--accent-color) 12%,transparent),transparent 70%)}}
    .genie{{display:block;width:300px;height:530px;object-fit:contain;filter:drop-shadow(0 12px 14px #00000014)}}
    .dialogue{{min-width:0}}.question-bubble{{position:relative;padding:24px;background:var(--surface-muted);border:1px solid var(--border-color);border-radius:var(--menu-radius)}}
    .question-bubble::before{{content:"";position:absolute;left:-13px;top:54px;width:24px;height:24px;background:var(--surface-muted);border-left:1px solid var(--border-color);border-bottom:1px solid var(--border-color);transform:rotate(45deg)}}
    .eyebrow{{margin:0 0 12px;color:var(--accent-color);font-size:17px;font-weight:600;position:relative}}
    h1{{font-size:28px;line-height:1.55;margin:0;overflow-wrap:anywhere;position:relative}}.description{{font-size:20px;line-height:1.6;margin:12px 0 0}}
    .options{{display:flex;flex-direction:column;gap:10px;margin-top:20px}}.option{{display:flex;align-items:center;gap:14px;min-height:54px;padding:10px 16px;border:1px solid var(--border-color);border-radius:12px;font-size:21px;background:var(--card-background-color)}}
    .option b{{display:flex;justify-content:center;align-items:center;min-width:32px;height:32px;border-radius:9px;background:var(--surface-accent);color:var(--accent-color);font-size:19px}}
    .option small{{margin-left:auto;color:var(--font-color-sub);font-size:16px}}footer{{padding-top:24px;border-top:1px solid var(--border-color);margin-top:22px;color:var(--font-color-sub);font-size:17px}}
    .portrait{{display:block;max-height:240px;max-width:100%;border-radius:14px;margin:20px auto 0;object-fit:contain}}.credit{{color:var(--font-color-sub);font-size:15px;text-align:center;margin:8px 0 0}}
    {custom_css}
    </style><main><header>AKINATOR · 网络天才<span>想好一个人物，让我来猜</span></header><div class="stage"><div class="genie-panel">{genie}</div><div class="dialogue"><div class="question-bubble"><p class="eyebrow">{title}</p>{body}</div>{portrait}<div class="options">{controls}</div></div></div><footer>{footer_text(state)}</footer></main></html>'''


async def render_card(state, *, photo=None, host=True):
    theme = theme_context(host)
    if HTML_RENDER_AVAILABLE:
        try:
            return await asyncio.wait_for(
                capture_html(card_html(state, photo=photo, theme=theme), host=host), 13
            )
        except Exception as exc:
            from nonebot import logger

            # Browser errors may contain session URLs; record only their type.
            logger.warning("Akinator 浏览器制图失败，改用本地图片卡片 ({})", type(exc).__name__)
    from .raster import render_png

    # Font loading, image decoding and PNG encoding must not block the bot loop.
    return await asyncio.to_thread(render_png, state, photo=photo, theme=theme)
