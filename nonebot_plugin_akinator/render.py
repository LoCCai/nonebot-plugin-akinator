"""Self-contained cards; screenshots never wait for remote fonts or portraits."""
from __future__ import annotations

import base64
import html
import re

from .const import DATA_AKITUDE_DIR, DATA_ADDITIONAL_CSS_PATH
from .integration import capture_html, theme_context


def card_html(state, *, photo=None, theme=None):
    theme = theme or {"palette_mode": "day"}
    dark = theme.get("palette_mode") == "night"
    bg, panel, ink, muted = ("#121827", "#1d2537", "#f2f4ff", "#adb6d0") if dark else ("#f1edf9", "#ffffff", "#28243d", "#6d6880")
    accent = str(theme.get("accent_rgb", "130,85,220"))
    if not re.fullmatch(r"\d{1,3},\s*\d{1,3},\s*\d{1,3}", accent):
        accent = "130,85,220"
    genie = ""
    if re.fullmatch(r"[a-z_]+\.png", state.akitude):
        path = DATA_AKITUDE_DIR / state.akitude
        if path.is_file() and path.stat().st_size < 3_000_000:
            genie = f'<img class="genie" src="data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}">'
    if state.guess:
        title = "我猜，你想的是……"
        body = f'<h1>{html.escape(state.guess.name)}</h1><p class="description">{html.escape(state.guess.description)}</p>'
        if photo:
            mime, data = photo
            body += f'<img class="portrait" src="data:{mime};base64,{base64.b64encode(data).decode()}">'
        if state.guess.pseudo and photo:
            body += f'<p class="credit">图片提供：{html.escape(state.guess.pseudo)}</p>'
        controls = '<div class="option">猜对了？回复「是」</div><div class="option">猜错了？回复「否」或「继续」</div>'
    else:
        title = f"第 {state.question_number} 个问题"
        body = f'<h1>{html.escape(state.question)}</h1>'
        controls = ''.join(f'<div class="option"><b>{i}</b> {text}</div>' for i, text in enumerate(("是", "否", "不知道", "可能是", "可能不是"), 1))
    footer = "回复文字或序号即可 · " + ("上一题 / B · " if state.answer_depth else "") + "退出 / E"
    try:
        custom_css = DATA_ADDITIONAL_CSS_PATH.read_text("utf-8")
    except OSError:
        custom_css = ""
    return f'''<!doctype html><html data-theme="{'dark' if dark else 'light'}"><meta charset="utf-8"><style>
    *{{box-sizing:border-box}}body{{margin:0;width:820px;padding:24px;background:{bg};color:{ink};font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}}
    main{{background:{panel};border-radius:24px;padding:34px;position:relative;overflow:hidden;border:1px solid rgba({accent},.22)}}
    header{{color:rgb({accent});font-weight:700;letter-spacing:2px;font-size:18px}}.eyebrow{{margin:26px 0 12px;color:{muted};font-size:19px}}
    h1{{font-size:32px;line-height:1.55;margin:0 0 24px;overflow-wrap:anywhere;position:relative}}.content{{position:relative;z-index:1}}
    .options{{display:flex;flex-wrap:wrap;gap:12px}}.option{{border-radius:12px;padding:14px 18px;background:rgba({accent},.09);font-size:21px}}
    .option b{{color:rgb({accent});margin-right:10px}}footer,.credit{{margin-top:26px;color:{muted};font-size:17px}}.description{{font-size:22px;line-height:1.6}}
    .portrait{{display:block;max-height:360px;max-width:100%;border-radius:16px;margin:20px auto;object-fit:contain}}
    .genie{{position:absolute;height:330px;right:-30px;top:30px;opacity:.08}}{theme.get('theme_css', '')}{custom_css}
    </style><main>{genie}<div class="content"><header>AKINATOR · 网络天才</header><p class="eyebrow">{title}</p>{body}<div class="options">{controls}</div><footer>{footer}</footer></div></main></html>'''


async def render_card(state, *, photo=None, host=True):
    return await capture_html(card_html(state, photo=photo, theme=theme_context(host)), host=host)
