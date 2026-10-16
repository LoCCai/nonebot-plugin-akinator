import asyncio
import time

from nonebot import get_driver, logger, on_command
from nonebot.adapters import Bot, Event, Message
from nonebot.exception import NoneBotException
from nonebot.params import CommandArg
from nonebot_plugin_waiter import waiter

from .config import config
from .game import GameError, InvalidAction
from .integration import recall_message, send_message
from .interaction import parse_action, session_key
from .message import build_message
from .runtime import Runtime, start_game
from .transport import Options

HELP = ("网络天才 · 猜人物\n先在心里想好一个人物，再发送 /aki 开局。\n"
        "答题：1 是、2 否、3 不知道、4 可能是、5 可能不是；也可回复文字。\n"
        "上一题 / B：撤销上一问；退出 / E：结束本局。\n"
        "出现猜测后：是 = 猜对了；否 / 继续 = 接着猜。\n"
        "只有本局发起者能作答；群聊、私聊和不同机器人之间互不影响。")

runtime = Runtime(config.akinator_max_sessions, config.akinator_request_concurrency,
                  config.akinator_admission_timeout, config.akinator_session_lifetime)
get_driver().on_shutdown(runtime.shutdown)
cmd_aki = on_command("akinator", aliases={"aki", "网络天才", "猜人物"}, priority=5, block=True)


async def send(bot, event, content):
    return await send_message(bot, event, content, host=config.akinator_host_integration)


async def play(bot, event, session, key):
    options = Options(
        base_url=config.akinator_base_url_template.format(config.akinator_language),
        proxy=config.akinator_proxy or config.proxy, timeout=config.akinator_request_timeout,
        headless=config.akinator_browser_headless, virtual_display=config.akinator_virtual_display,
        executable_path=config.akinator_browser_executable,
    )
    await send(bot, event, "先在心里想好一个人物，我来问你……")
    async with runtime.request():
        session.game = await start_game(config.akinator_client_type, options,
                                        child_mode=config.akinator_child_mode, timeout=config.akinator_start_timeout)
    game = session.game
    previous = None
    while not game.state.ended:
        remaining = session.expires_at - time.monotonic()
        if remaining <= 0:
            await send(bot, event, "这局游戏时间较长，已结束。想继续的话，再发送 /aki 开局吧。")
            return

        # Rendering must not consume the player's answer timeout. Register the
        # waiter after rendering but before delivery, so quick replies are kept.
        content = await build_message(game.state)
        remaining = session.expires_at - time.monotonic()
        if remaining <= 0:
            await send(bot, event, "这局游戏时间较长，已结束。想继续的话，再发送 /aki 开局吧。")
            return

        @waiter(waits=["message"], keep_session=True)
        async def action_waiter(bot: Bot, event: Event):
            if session_key(bot, event) != key:
                return None
            return parse_action(event.get_plaintext(), proposal=game.state.guess is not None)

        waiting = asyncio.create_task(action_waiter.wait(timeout=min(config.akinator_operation_timeout, remaining)))
        try:
            if previous and config.akinator_recall_previous:
                await recall_message(bot, previous, host=config.akinator_host_integration)
            previous = await send(bot, event, content)
            action = await waiting
        finally:
            if not waiting.done():
                waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
        if action is None:
            await send(bot, event, "等待回答超时，本局已结束。发送 /aki 可以重新开始。")
            return
        if action == "exit":
            await send(bot, event, "已退出本局游戏。")
            return
        try:
            async with runtime.request():
                operation = (game.back() if action == "back" else game.choose() if action == "choose"
                             else game.exclude() if action == "exclude" else game.answer(action))
                await asyncio.wait_for(operation, config.akinator_request_timeout + 1)
        except InvalidAction as exc:
            await send(bot, event, str(exc))
            continue
        except asyncio.TimeoutError:
            if action == "choose" and game.state.confirmed:
                game.state.confirmation_error_type = "TimeoutError"
            else:
                raise
        if game.state.ended:
            if game.state.child_blocked:
                await send(bot, event, "这次猜测的内容不适合展示，本局已结束。换个人物再试试吧。")
            elif action == "choose":
                if not game.state.confirmation_recorded:
                    logger.warning("Akinator 上游统计未确认，本局按玩家确认结束 ({})", game.state.confirmation_error_type)
                await send(bot, event, f"猜中了！你想的是「{game.state.guess.name}」。下次再来挑战我吧。")
            else:
                await send(bot, event, "这次我没猜出来，是你赢啦！发送 /aki 可以再玩一局。")


@cmd_aki.handle()
async def handle_game(bot: Bot, event: Event, args: Message = CommandArg()):
    argument = args.extract_plain_text().strip().lower()
    if argument:
        await send(bot, event, HELP)
        return
    try:
        async with runtime.session(session_key(bot, event)) as session:
            await play(bot, event, session, session_key(bot, event))
    except NoneBotException:
        raise
    except GameError as exc:
        await send(bot, event, str(exc))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Exception strings from HTTP/browser libraries may contain session URLs.
        logger.warning("Akinator 本局停止 ({})", type(exc).__name__)
        # Never repeat an upstream answer or an uncertain outbound delivery.
        if not runtime.stopping:
            try:
                await send(bot, event, "本局请求未能完成，已结束游戏。请稍后发送 /aki 重新开始。")
            except Exception as delivery_error:
                logger.warning("Akinator 结束提示未送达 ({})", type(delivery_error).__name__)
