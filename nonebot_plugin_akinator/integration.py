"""Optional host utilities, with bundled implementations for other NoneBot bots."""
from __future__ import annotations

import asyncio
import importlib
import inspect


def optional_callable(module, name, enabled=True):
    if not enabled:
        return None
    try:
        value = getattr(importlib.import_module(module), name)
        return value if callable(value) else None
    except Exception:
        # An unrelated host utility may exist but have missing optional imports.
        return None


def compatible(function, *args, **kwargs):
    if function is None:
        return False
    try:
        inspect.signature(function).bind(*args, **kwargs)
        return True
    except (ValueError, TypeError):
        return False


async def send_message(bot, event, message, *, host=True):
    from nonebot_plugin_alconna.uniseg import UniMessage

    message = message if isinstance(message, UniMessage) else UniMessage.text(message)
    helper = optional_callable("src.utils.message_fx", "send_normal_message", host)
    if bot.adapter.get_name() == "OneBot V11" and compatible(helper, bot, event, None):
        exported = await (UniMessage.at(event.get_user_id()) + " " + message).export(bot=bot) if getattr(event, "group_id", None) else await message.export(bot=bot)
        # Once delivery starts, propagate errors. Never replay an unknown send.
        result = await helper(bot, event, exported)
        if result is None:
            raise RuntimeError("Host delivery did not confirm a message receipt")
        return ("host", result)
    return ("native", await message.send(target=event, bot=bot, at_sender=True))


async def recall_message(bot, receipt, *, host=True):
    if not receipt:
        return
    try:
        if receipt[0] == "host":
            helper = optional_callable("src.utils.onebot_recall", "recall_message", host)
            if compatible(helper, bot, message_id=receipt[1]):
                await asyncio.wait_for(helper(bot, message_id=receipt[1]), 5)
            else:
                await asyncio.wait_for(bot.call_api("delete_msg", message_id=receipt[1]), 5)
        else:
            await asyncio.wait_for(receipt[1].recall(), 5)
    except Exception:
        # A failed optional recall must not invalidate an accepted answer.
        pass


def theme_context(host=True):
    helper = optional_callable("src.utils.render_theme", "stylesheet_context", host)
    if compatible(helper, "bot/akinator.css"):
        try:
            result = helper("bot/akinator.css")
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    return {"theme": "day", "palette_mode": "day", "theme_css": "", "accent_rgb": "130,85,220"}


async def capture_html(document, *, host=True):
    helper = optional_callable("src.utils.bounded_htmlrender", "render_bounded_local_html", host)
    # The host renderer navigates to base_url before set_content. Cards embed
    # all assets, so an invented origin would turn every card into a DNS/proxy
    # failure and silently activate the text fallback.
    # Full-page captures should follow the card's natural height rather than
    # append blank space up to a fixed 600px viewport.
    kwargs = dict(base_url="about:blank", wait_ms=0, width=820, height=1,
                  device_scale_factor=1.5, timeout_ms=10000)
    if compatible(helper, document, **kwargs):
        return await helper(document, **kwargs)
    from nonebot_plugin_htmlrender import get_new_page

    async def capture():
        async with get_new_page(viewport={"width": 820, "height": 600}, device_scale_factor=1.5) as page:
            await page.set_content(document, wait_until="domcontentloaded", timeout=10000)
            return await page.locator("main").screenshot(type="png", timeout=10000, animations="disabled")
    return await asyncio.wait_for(capture(), 13)
