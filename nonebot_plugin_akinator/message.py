from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from nonebot import logger
from nonebot_plugin_alconna.uniseg import UniMessage

from .config import config
from .const import DATA_AKITUDE_DIR, HTML_RENDER_AVAILABLE, PILLOW_AVAILABLE


def state_text(state):
    if state.guess:
        guess = state.guess
        return (f"我猜：{guess.name}\n{guess.description}\n\n"
                "猜对了回复“是”；猜错了回复“否”或“继续”。\n退出 / E")
    return (f"第 {state.question_number} 题：{state.question}\n\n"
            "1. 是 / Y　2. 否 / N　3. 不知道 / IDK\n"
            "4. 可能是 / P　5. 可能不是 / PN\n"
            + ("上一题 / B　" if state.answer_depth else "") + "退出 / E")


async def download_image(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    async def download():
        async with httpx.AsyncClient(proxy=config.akinator_proxy or config.proxy, trust_env=False, timeout=4) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                mime = response.headers.get("content-type", "").split(";", 1)[0]
                if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                    return None
                result = bytearray()
                async for chunk in response.aiter_bytes():
                    result.extend(chunk)
                    if len(result) > 2_000_000:
                        return None
                return mime, bytes(result)
    try:
        return await asyncio.wait_for(download(), 5)
    except Exception:
        return None


async def get_photo(guess):
    return await download_image(guess.photo) if guess and guess.photo else None


async def warm_genie(state):
    from .visual import genie_name

    filename = genie_name(state)
    path = DATA_AKITUDE_DIR / filename
    if path.is_file() and 0 < path.stat().st_size < 3_000_000:
        return
    base = config.akinator_base_url_template.format(config.akinator_language).rstrip('/')
    asset = await download_image(f'{base}/assets/imgs/akitudes_670x1096/{filename}')
    if not asset or asset[0] != 'image/png' or not asset[1].startswith(b'\x89PNG\r\n\x1a\n'):
        return
    temporary = path.with_name(f'.{filename}.{uuid4().hex}.tmp')
    try:
        DATA_AKITUDE_DIR.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(asset[1])
        os.replace(temporary, path)
    except OSError:
        pass
    finally:
        temporary.unlink(missing_ok=True)


async def build_message(state):
    if not config.akinator_text_mode and (HTML_RENDER_AVAILABLE or PILLOW_AVAILABLE):
        try:
            from .render import render_card
            photo, _ = await asyncio.gather(get_photo(state.guess), warm_genie(state))
            image = await render_card(state, photo=photo, host=config.akinator_host_integration)
            return UniMessage.image(raw=image)
        except Exception as exc:
            logger.warning("Akinator 卡片生成失败，改用文字继续本局 ({})", type(exc).__name__)
    return UniMessage.text(state_text(state))
