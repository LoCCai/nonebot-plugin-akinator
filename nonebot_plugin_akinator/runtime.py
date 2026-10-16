"""Bound sessions and upstream work without depending on a bot framework."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import time

from .game import Game, GameError
from .transport import BrowserTransport, HTTPTransport


class Busy(GameError):
    pass


@dataclass
class Session:
    task: asyncio.Task
    expires_at: float
    game: Game | None = None


class Runtime:
    def __init__(self, max_sessions=4, concurrency=2, admission_timeout=3, lifetime=1200):
        self.max_sessions = max_sessions
        self.admission_timeout = admission_timeout
        self.lifetime = lifetime
        self.sessions: dict[tuple, Session] = {}
        self.requests = asyncio.Semaphore(concurrency)
        self.stopping = False

    @asynccontextmanager
    async def session(self, key):
        if self.stopping:
            raise Busy("游戏服务正在停止，请稍后再试。")
        if key in self.sessions:
            raise Busy("你在当前聊天已有一局游戏，请直接回答，或发送“退出”。")
        if len(self.sessions) >= self.max_sessions:
            raise Busy("当前游戏人数较多，请稍后再开局。")
        session = Session(asyncio.current_task(), time.monotonic() + self.lifetime)
        self.sessions[key] = session
        try:
            yield session
        finally:
            self.sessions.pop(key, None)
            if session.game:
                await session.game.close()

    @asynccontextmanager
    async def request(self):
        try:
            await asyncio.wait_for(self.requests.acquire(), self.admission_timeout)
        except asyncio.TimeoutError:
            raise Busy("上游服务繁忙，请稍后再开局。") from None
        try:
            if self.stopping:
                raise Busy("游戏服务正在停止，请稍后再试。")
            yield
        finally:
            self.requests.release()

    async def shutdown(self):
        self.stopping = True
        tasks = {session.task for session in self.sessions.values()} - {asyncio.current_task()}
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def start_game(mode, options, *, child_mode, timeout):
    """Auto fallback creates a new game only; answers are never replayed."""
    transports = {"httpx": (HTTPTransport,), "playwright": (BrowserTransport,),
                  "auto": (HTTPTransport, BrowserTransport)}[mode]
    for index, transport in enumerate(transports):
        game = Game(transport(options), child_mode=child_mode)
        try:
            await asyncio.wait_for(game.start(), timeout)
            return game
        except BaseException as exc:
            await game.close()
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)) or index == len(transports) - 1:
                raise
