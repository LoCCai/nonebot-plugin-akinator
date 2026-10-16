"""Isolated upstream clients. Mutating requests are deliberately never retried."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from .game import GameError, UpstreamBlocked


@dataclass
class Options:
    base_url: str = "https://cn.akinator.com"
    proxy: str | None = field(default=None, repr=False)
    timeout: float = 20
    headless: bool = True
    virtual_display: bool = False
    executable_path: str | None = None

    def __post_init__(self):
        parts = urlsplit(self.base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("Akinator base URL must be an HTTP(S) URL without credentials")
        self.base_url = self.base_url.rstrip("/")


def check_response(status: int, text: str) -> str:
    if status in {403, 429, 503}:
        raise UpstreamBlocked("上游暂时拒绝访问，请稍后再开局。")
    if not 200 <= status < 300:
        raise GameError(f"上游服务异常（HTTP {status}），请稍后重新开局。")
    if any(marker in text.lower() for marker in ("cf-chl-", "challenge-platform", "just a moment...")):
        raise UpstreamBlocked("上游需要网页验证，本局无法继续，请稍后再试。")
    return text


class HTTPTransport:
    def __init__(self, options: Options):
        self.options = options
        self.client = httpx.AsyncClient(
            proxy=options.proxy, timeout=options.timeout, follow_redirects=True,
            trust_env=False, headers={"User-Agent": "Mozilla/5.0", "Referer": options.base_url + "/"},
        )

    async def start(self, fields):
        return await self.post("game", fields)

    async def post(self, path, fields):
        response = await self.client.post(self.options.base_url + "/" + path, data=fields)
        return check_response(response.status_code, response.text)

    async def close(self):
        await self.client.aclose()


def browser_proxy(value: str | None):
    if not value:
        return None
    parts = urlsplit(value)
    if not parts.scheme or not parts.hostname:
        raise ValueError("Invalid Akinator proxy URL")
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    options = {"server": urlunsplit((parts.scheme, host + (f":{parts.port}" if parts.port else ""), "", "", ""))}
    if parts.username:
        options["username"] = unquote(parts.username)
    if parts.password:
        options["password"] = unquote(parts.password)
    return options


class BrowserTransport:
    """A dedicated browser per game; never reconfigure htmlrender or global DISPLAY."""

    def __init__(self, options: Options):
        self.options = options
        self.playwright = self.browser = self.page = self.display = None

    async def _open(self):
        from playwright.async_api import async_playwright

        launch_env = dict(os.environ)
        if not self.options.headless and self.options.virtual_display:
            self.display = await asyncio.create_subprocess_exec(
                "Xvfb", "-displayfd", "1", "-screen", "0", "1280x900x24", "-nolisten", "tcp", "-ac",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            number = (await asyncio.wait_for(self.display.stdout.readline(), 5)).decode().strip()
            if not number.isdigit():
                raise GameError("Akinator 独立显示服务未能启动。")
            launch_env["DISPLAY"] = ":" + number
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.options.headless, proxy=browser_proxy(self.options.proxy),
            executable_path=self.options.executable_path, env=launch_env,
            args=["--disable-dev-shm-usage"], timeout=int(self.options.timeout * 1000),
        )
        context = await self.browser.new_context(viewport={"width": 1100, "height": 850})
        self.page = await context.new_page()
        self.page.set_default_timeout(self.options.timeout * 1000)

    async def start(self, fields):
        await self._open()
        response = await self.page.goto(self.options.base_url, wait_until="domcontentloaded")
        if response is not None and response.status >= 400:
            check_response(response.status, "")
        form = await self.page.wait_for_selector("#formTheme", state="attached")
        async with self.page.expect_navigation(wait_until="domcontentloaded"):
            await form.evaluate("""(form, args) => {
                for (const [key, value] of Object.entries(args.fields)) {
                    let input = form.querySelector(`[name="${key}"]`);
                    if (!input) {
                        input = document.createElement('input'); input.type = 'hidden';
                        input.name = key; form.appendChild(input);
                    }
                    input.value = value;
                }
                form.action = args.url; form.submit();
            }""", {"fields": fields, "url": self.options.base_url + "/game"})
        return check_response(200, await self.page.content())

    async def post(self, path, fields):
        if self.page is None:
            raise GameError("Akinator 会话尚未建立。")
        # Pass arguments as data, never interpolate session fields into JavaScript.
        response = await self.page.evaluate("""async (args) => {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), args.timeout);
            try {
                const response = await fetch(args.url, {
                    method: 'POST', credentials: 'same-origin',
                    body: new URLSearchParams(args.fields), signal: controller.signal
                });
                return {status: response.status, text: await response.text()};
            } finally { clearTimeout(timer); }
        }""", {"url": self.options.base_url + "/" + path, "fields": fields,
                  "timeout": int(self.options.timeout * 1000)})
        return check_response(response["status"], response["text"])

    async def close(self):
        # Close only resources owned by this transport, including partial starts.
        for name in ("browser", "playwright"):
            resource = getattr(self, name)
            setattr(self, name, None)
            if resource:
                try:
                    await asyncio.wait_for(resource.close() if name == "browser" else resource.stop(), 5)
                except Exception:
                    pass
        self.page = None
        if self.display:
            display, self.display = self.display, None
            if display.returncode is None:
                display.terminate()
                try:
                    await asyncio.wait_for(display.wait(), 3)
                except asyncio.TimeoutError:
                    display.kill()
                    await display.wait()
