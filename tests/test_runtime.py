import asyncio
import pytest

from akinator_core_test import runtime as module
from akinator_core_test.game import GameError
from akinator_core_test.runtime import Busy, Runtime, start_game
from akinator_core_test.transport import Options
from test_game import CURRENT, Transport


async def test_sessions_reserve_before_start_and_release_on_failure():
    runtime = Runtime(max_sessions=1)
    with pytest.raises(ValueError):
        async with runtime.session(("bot", "chat", "user")):
            with pytest.raises(Busy):
                async with runtime.session(("bot", "chat", "user")):
                    pass
            with pytest.raises(Busy):
                async with runtime.session(("bot", "other", "user")):
                    pass
            raise ValueError
    assert runtime.sessions == {}


async def test_shutdown_cancels_wait_and_closes_session():
    runtime = Runtime()
    closed = asyncio.Event()
    entered = asyncio.Event()
    class Game:
        async def close(self):
            closed.set()
    async def run():
        async with runtime.session((1,)) as session:
            session.game = Game()
            entered.set()
            await asyncio.Future()
    task = asyncio.create_task(run())
    await entered.wait()
    await runtime.shutdown()
    assert task.cancelled() and closed.is_set() and not runtime.sessions
    with pytest.raises(Busy):
        async with runtime.session((1,)):
            pass


async def test_request_admission_is_bounded_and_capacity_recovers():
    runtime = Runtime(concurrency=1, admission_timeout=.01)
    async with runtime.request():
        with pytest.raises(Busy):
            async with runtime.request():
                pass
    async with runtime.request():
        pass


async def test_auto_fallback_only_at_start_closes_first_transport(monkeypatch):
    clients = []
    class HTTP(Transport):
        def __init__(self, _):
            super().__init__(start="denied")
            clients.append(self)
    class Browser(HTTP):
        async def start(self, fields):
            return CURRENT
    monkeypatch.setattr(module, "HTTPTransport", HTTP)
    monkeypatch.setattr(module, "BrowserTransport", Browser)
    game = await start_game("auto", Options(), child_mode=True, timeout=1)
    assert len(clients) == 2 and clients[0].closed == 1 and clients[1].closed == 0
    await game.close()
    assert clients[1].closed == 1


async def test_cancel_start_closes_partial_client_without_fallback(monkeypatch):
    clients = []
    class HTTP(Transport):
        def __init__(self, _):
            super().__init__()
            clients.append(self)
        async def start(self, fields):
            raise asyncio.CancelledError
    monkeypatch.setattr(module, "HTTPTransport", HTTP)
    with pytest.raises(asyncio.CancelledError):
        await start_game("auto", Options(), child_mode=True, timeout=1)
    assert len(clients) == 1 and clients[0].closed == 1
