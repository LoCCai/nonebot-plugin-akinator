"""Exercise real NoneBot dispatch and waiter priorities, without QQ or HTTP."""
import asyncio
from pathlib import Path
import subprocess
import sys


def test_game_input_through_nonebot_dispatch(tmp_path):
    result = subprocess.run(
        [sys.executable, __file__, str(Path(__file__).resolve().parents[1])],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DISPATCH_VERIFIED" in result.stdout


async def dispatch_scenario():
    import json
    import nonebot
    from nonebot.adapters import Adapter, Bot
    from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
    from nonebot.message import handle_event
    from nonebot.matcher import matchers

    nonebot.init(driver="~none", _env_file=None, akinator_text_mode=True)
    sys.path.insert(0, sys.argv[1])
    assert nonebot.load_plugin("nonebot_plugin_akinator") is not None
    from nonebot_plugin_akinator import __main__ as runner
    from nonebot_plugin_akinator.game import Game

    class TestAdapter(Adapter):
        @classmethod
        def get_name(cls):
            return "IsolatedDispatch"

        async def _call_api(self, bot, api, **data):
            raise AssertionError("No real outbound API permitted")

    class TestBot(Bot):
        async def send(self, event, message, **kwargs):
            raise AssertionError("No real outbound messages permitted")

    bot = TestBot(TestAdapter(nonebot.get_driver()), "7001")
    other_bot = TestBot(bot.adapter, "7002")
    messages, observed, games = [], [], []
    rendering, release_render = asyncio.Event(), asyncio.Event()
    hold_render = False
    timeout_back = False

    class Transport:
        def __init__(self):
            self.calls = []
            self.closed = 0

        async def start(self, fields):
            return '<input name="session" value="synthetic"><p id="question-label">第一题</p>'

        async def post(self, path, fields):
            self.calls.append((path, fields))
            if path == "cancel_answer" and timeout_back:
                raise asyncio.TimeoutError()
            return json.dumps({"question": "第一题" if path == "cancel_answer" else "第二题",
                               "step": len(self.calls), "progression": 1})

        async def close(self):
            self.closed += 1

    async def start(*args, **kwargs):
        game = Game(Transport())
        await game.start()
        games.append(game)
        return game

    async def card(state):
        if hold_render and state.question_number == 2:
            rendering.set()
            await release_render.wait()
        return f"card:{state.question_number}"

    async def send(bot, event, content):
        messages.append(str(content))
        await asyncio.sleep(0)
        return "receipt"

    runner.start_game, runner.build_message, runner.send = start, card, send
    observer = nonebot.on_message(priority=10, block=False)

    @observer.handle()
    async def observe(event: GroupMessageEvent):
        observed.append(event.get_plaintext())

    def event(text, *, user=9001, group=8001):
        return GroupMessageEvent(
            time=1, self_id=7001, post_type="message", message_type="group", sub_type="normal",
            user_id=user, group_id=group, message_id=1, message=Message(text), raw_message=text,
            font=0, sender={"user_id": user, "role": "member"},
        )

    async def until(predicate):
        async def check():
            while not predicate():
                await asyncio.sleep(0.001)
        await asyncio.wait_for(check(), 3)

    def ready():
        return any(s.stage == "waiting" for s in runner.runtime.sessions.values())

    baseline = {p: len(matchers[p]) for p in (0, 1)}
    playing = asyncio.create_task(handle_event(bot, event("/aki")))
    await until(ready)
    original_waiter = tuple(matchers[0])
    for test_bot, input_event in ((bot, event("B", user=9002)), (bot, event("B", group=8002)),
                                  (other_bot, event("B")), (bot, event("无关聊天")), (bot, event("/其他命令"))):
        before = len(messages)
        await handle_event(test_bot, input_event)
        assert len(messages) == before
    assert observed[-2:] == ["无关聊天", "/其他命令"]

    await handle_event(bot, event("0"))
    assert "请输入 1—5" in messages[-1]
    assert tuple(matchers[0]) == original_waiter and not games[-1].transport.calls
    assert "0" not in observed
    await handle_event(bot, event("B"))
    assert "已经是第一题" in messages[-1]
    assert tuple(matchers[0]) == original_waiter and messages.count("card:1") == 1

    hold_render = True
    await handle_event(bot, event("1"))
    await asyncio.wait_for(rendering.wait(), 3)
    assert games[-1].transport.calls[0][1]["answer"] == "0"
    await handle_event(bot, event("B"))
    assert "正在处理上一步或发送题卡" in messages[-1]
    await handle_event(bot, event("0"))
    assert "请输入 1—5" in messages[-1]
    assert len(games[-1].transport.calls) == 1
    hold_render = False
    release_render.set()
    await until(ready)
    await handle_event(bot, event("B"))
    await until(lambda: messages.count("card:1") == 2 and ready())
    assert "正在返回上一题，请稍候。" in messages
    assert [path for path, _ in games[-1].transport.calls] == ["answer", "cancel_answer"]
    assert games[-1].state.answer_depth == 0
    await handle_event(bot, event("6"))
    assert "请输入 1—5" in messages[-1]
    await handle_event(bot, event("2"))
    await until(lambda: messages.count("card:2") == 2 and ready())
    await handle_event(bot, event("E"))
    await asyncio.wait_for(playing, 3)
    assert messages[-1] == "已退出本局游戏。"
    assert games[-1].transport.closed == 1 and not runner.runtime.sessions
    assert {p: len(matchers[p]) for p in (0, 1)} == baseline

    # A real upstream timeout has an operation-specific response and is never
    # replayed. Verify both listeners and transport are cleaned up afterwards.
    timeout_back = True
    playing = asyncio.create_task(handle_event(bot, event("/aki")))
    await until(ready)
    await handle_event(bot, event("1"))
    await until(lambda: games[-1].state.answer_depth == 1 and ready())
    await handle_event(bot, event("B"))
    await asyncio.wait_for(playing, 3)
    assert "返回上一题请求超时" in messages[-1]
    assert [path for path, _ in games[-1].transport.calls] == ["answer", "cancel_answer"]
    assert games[-1].transport.closed == 1 and not runner.runtime.sessions
    assert {p: len(matchers[p]) for p in (0, 1)} == baseline

    playing = asyncio.create_task(handle_event(bot, event("/aki")))
    await until(ready)
    await runner.runtime.shutdown()
    await asyncio.wait_for(playing, 3)
    assert games[-1].transport.closed == 1 and not runner.runtime.sessions
    assert {p: len(matchers[p]) for p in (0, 1)} == baseline
    print("DISPATCH_VERIFIED")


if __name__ == "__main__":
    asyncio.run(dispatch_scenario())
