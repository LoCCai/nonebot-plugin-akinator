"""Input semantics shared by all supported chat adapters."""
import re
import unicodedata

from .game import Answer


ANSWERS = {
    Answer.YES: {"1", "y", "yes", "是", "s", "真", "true", "对", "猜对了"},
    Answer.NO: {"2", "n", "no", "否", "f", "不是", "bs", "假", "false", "不对", "猜错了"},
    Answer.I_DONT_KNOW: {"3", "i", "idk", "i dont know", "i don't know", "不知道", "bzd", "不清楚", "bqc"},
    Answer.PROBABLY: {"4", "p", "probably", "或许是", "hxx", "可能是", "kns"},
    Answer.PROBABLY_NOT: {"5", "pn", "probably not", "或许不是", "hxbs", "可能不是", "knbs"},
}
BACK = {"b", "back", "prev", "previous", "上一问", "syw", "上一题", "syt", "上一个", "syg"}
EXIT = {"e", "exit", "退出", "q", "quit", "tc", "不玩了", "bwl"}
CONTINUE = {"c", "continue", "继续"}


def parse_action(text, *, proposal=False):
    text = unicodedata.normalize("NFKC", text).strip().lower()
    if text in EXIT:
        return "exit"
    if text in BACK:
        return "back"
    if proposal:
        if text in ANSWERS[Answer.YES]:
            return "choose"
        if text in ANSWERS[Answer.NO] | CONTINUE:
            return "exclude"
    else:
        answer = next((answer for answer, words in ANSWERS.items() if text in words), None)
        if answer is not None:
            return answer
    # Give feedback for attempted answers, without taking over conversation or
    # other plugins' commands. Numeric input is a choice even outside 1--5.
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?|[a-z]", text) or any(text in words for words in ANSWERS.values()):
        return "invalid"
    return None


def answer_hint(*, proposal=False):
    if proposal:
        return "请回复 1 / 是确认猜中，2 / 否 / 继续接着猜；B 返回上一题，E 退出。本次输入未改变游戏。"
    return "请输入 1—5：1 是、2 否、3 不知道、4 可能是、5 可能不是；也可回复 Y/N/IDK/P/PN。B 返回上一题，E 退出。本次输入未改变游戏。"


def session_key(bot, event):
    return (bot.adapter.get_name(), str(bot.self_id), event.get_session_id(), event.get_user_id())
