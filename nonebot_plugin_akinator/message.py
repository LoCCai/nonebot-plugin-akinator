from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx
from nonebot import logger
from nonebot_plugin_alconna.uniseg import UniMessage

from .config import config
from .const import HTML_RENDER_AVAILABLE


def state_text(state):
    if state.guess:
        guess = state.guess
        return (f"我猜：{guess.name}\n{guess.description}\n\n"
                "猜对了回复“是”；猜错了回复“否”或“继续”。\n退出 / E")
    return (f"第 {state.question_number} 题：{state.question}\n\n"
            "1. 是 / Y　2. 否 / N　3. 不知道 / IDK\n"
            "4. 可能是 / P　5. 可能不是 / PN\n"
            + ("上一题 / B　" if state.answer_depth else "") + "退出 / E")


async def get_photo(guess):
    if not guess or not guess.photo:
        return None
    parts = urlsplit(guess.photo)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    async def download():
        async with httpx.AsyncClient(proxy=config.akinator_proxy or config.proxy, trust_env=False, timeout=4) as client:
            async with client.stream("GET", guess.photo) as response:
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


async def build_message(state):
    if not config.akinator_text_mode and HTML_RENDER_AVAILABLE:
        try:
            from .render import render_card
            image = await render_card(state, photo=await get_photo(state.guess), host=config.akinator_host_integration)
            return UniMessage.image(raw=image)
        except Exception as exc:
            logger.warning("Akinator 卡片生成失败，改用文字继续本局 ({})", type(exc).__name__)
    return UniMessage.text(state_text(state))
