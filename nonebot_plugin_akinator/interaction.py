"""Input semantics shared by all supported chat adapters."""
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
    text = text.strip().lower()
    if text in EXIT:
        return "exit"
    if text in BACK:
        return "back"
    if proposal:
        if text in ANSWERS[Answer.YES]:
            return "choose"
        if text in ANSWERS[Answer.NO] | CONTINUE:
            return "exclude"
        return None
    return next((answer for answer, words in ANSWERS.items() if text in words), None)


def session_key(bot, event):
    return (bot.adapter.get_name(), str(bot.self_id), event.get_session_id(), event.get_user_id())
