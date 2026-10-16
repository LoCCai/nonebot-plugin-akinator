import pytest
from akinator_core_test.game import Answer
from akinator_core_test.interaction import parse_action, session_key


@pytest.mark.parametrize("text,expected", [("1", Answer.YES), ("否", Answer.NO), ("idk", Answer.I_DONT_KNOW),
                                         ("4", Answer.PROBABLY), ("PN", Answer.PROBABLY_NOT),
                                         ("上一题", "back"), ("退出", "exit"), ("无关聊天", None), ("/其他命令", None)])
def test_answer_choices_and_unrelated_messages(text, expected):
    assert parse_action(text) == expected


@pytest.mark.parametrize("text,expected", [("是", "choose"), ("1", "choose"), ("否", "exclude"),
                                         ("2", "exclude"), ("继续", "exclude"), ("3", None), ("退出", "exit")])
def test_proposal_confirmation_is_separate_from_answering(text, expected):
    assert parse_action(text, proposal=True) == expected


def test_scope_includes_adapter_bot_chat_and_user():
    class Adapter:
        def get_name(self): return "test"
    class Bot:
        adapter = Adapter()
        self_id = "first-bot"
    class Event:
        def get_session_id(self): return "chat"
        def get_user_id(self): return "user"
    bot, event = Bot(), Event()
    first = session_key(bot, event)
    bot.self_id = "other-bot"
    assert session_key(bot, event) != first
    bot.self_id = "first-bot"
    event.get_user_id = lambda: "other-user"
    assert session_key(bot, event) != first
