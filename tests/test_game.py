import asyncio
import json

import pytest

from akinator_core_test.game import Answer, Game, GameError, InvalidAction, parse_response, parse_start

CURRENT = '''<p id="question-label">他是&lt;游戏&gt;人物吗？</p>
<script>localStorage.setItem('session', 'private-session');
localStorage.setItem('identifiant', 'private-id');
localStorage.setItem('step', '1');</script>'''
LEGACY = '''<p id="question-label">他是<strong>真人</strong>吗？</p>
<script>$('#session').val('private-session');$('#signature').val('private-signature');</script>
<input name="identifiant" value="private-id">'''
PROPOSAL = {"completion": "OK", "step": "24", "progression": "95", "id_proposition": "123",
            "name_proposition": "孙悟空", "description_proposition": "西游记中的人物", "photo": "https://example.com/monkey.png"}


class Transport:
    def __init__(self, responses=(), start=CURRENT):
        self.document = start
        self.responses = list(responses)
        self.calls = []
        self.closed = 0

    async def start(self, fields):
        self.calls.append(("game", fields))
        return self.document

    async def post(self, path, fields):
        self.calls.append((path, fields))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response if isinstance(response, str) else json.dumps(response)

    async def close(self):
        self.closed += 1


@pytest.mark.parametrize("document,signature", [(CURRENT, None), (LEGACY, "private-signature")])
def test_new_and_legacy_start(document, signature):
    state = parse_start(document)
    assert state["session"] == "private-session"
    assert state["signature"] == signature
    assert state["identifiant"] == "private-id"
    assert state["question"]


@pytest.mark.parametrize("document", ["", "<html>challenge</html>", CURRENT.replace("'1'", "'nan'")])
def test_invalid_start(document):
    with pytest.raises(GameError):
        parse_start(document)


async def test_answer_then_undo_uses_server_cursor_and_local_question_number():
    transport = Transport([{"question": "第二题", "step": "2", "progression": "3"},
                           {"question": "第一题", "step": "3", "progression": "0"}])
    game = Game(transport)
    state = await game.start()
    assert state.question_number == 1
    with pytest.raises(InvalidAction):
        await game.back()
    await game.answer(Answer.I_DONT_KNOW)
    assert state.question_number == 2
    await game.back()
    assert state.step == 3 and state.question_number == 1
    assert transport.calls[1][1]["answer"] == "2"
    assert transport.calls[2][1]["step"] == "2"
    assert "signature" not in transport.calls[1][1]
    assert "private-session" not in repr(state) and "private-id" not in repr(state)
    await game.close()
    await game.close()
    assert transport.closed == 1


@pytest.mark.parametrize("answer", list(Answer))
async def test_all_answer_ids(answer):
    transport = Transport([{"question": "next", "step": 2}])
    game = Game(transport)
    await game.start()
    await game.answer(answer)
    assert transport.calls[-1][1]["answer"] == str(answer.value)


async def test_guess_confirm_payload_and_end():
    transport = Transport([PROPOSAL, "<html>confirmed</html>"])
    game = Game(transport)
    await game.start()
    await game.answer(Answer.YES)
    assert game.state.guess.name == "孙悟空"
    with pytest.raises(InvalidAction):
        await game.answer(Answer.NO)
    await game.choose()
    path, fields = transport.calls[-1]
    assert path == "choice" and fields["identifiant"] == "private-id" and fields["pid"] == "123"
    assert game.state.ended
    assert game.state.confirmed and game.state.confirmation_recorded
    with pytest.raises(InvalidAction):
        await game.choose()


@pytest.mark.parametrize("error", [GameError("HTTP 500"), asyncio.TimeoutError()])
async def test_upstream_statistics_failure_keeps_player_confirmed_outcome(error):
    transport = Transport([PROPOSAL, error])
    game = Game(transport)
    await game.start()
    await game.answer(Answer.YES)
    state = await game.choose()
    assert state.ended and state.confirmed and not state.confirmation_recorded
    assert state.confirmation_error_type == type(error).__name__
    assert [path for path, _ in transport.calls] == ["game", "answer", "choice"]
    assert set(transport.calls[-1][1]) == {"step", "sid", "session", "identifiant", "pid", "charac_name", "charac_desc", "pflag_photo"}


async def test_wrong_guess_continues_with_correct_fields():
    transport = Transport([PROPOSAL, {"question": "继续的问题", "step": 25}])
    game = Game(transport)
    await game.start()
    await game.answer(Answer.YES)
    await game.exclude()
    assert game.state.guess is None and not game.state.ended
    assert transport.calls[-1][0] == "exclude" and transport.calls[-1][1]["forward_answer"] == "1"


async def test_no_questions_left_terminal_can_be_pre_wrapped_json():
    transport = Transport([{**PROPOSAL, "no_question": "1"}, '<pre>{"completion":"OK","step":25}</pre>'])
    game = Game(transport)
    await game.start()
    await game.answer(Answer.YES)
    await game.exclude()
    assert game.state.ended and game.state.guess is None
    assert transport.calls[-1][1]["forward_answer"] == "0"


async def test_child_mode_hides_blocked_guess_entirely():
    game = Game(Transport([{**PROPOSAL, "valide_contrainte": "0"}]), child_mode=True)
    await game.start()
    state = await game.answer(Answer.YES)
    assert state.ended and state.child_blocked and state.guess is None


@pytest.mark.parametrize("document", ["", "[]", '{"completion":"KO"}', '{"completion":"KO - TIMEOUT"}',
                                      '{"completion":"UNKNOWN","question":"x"}', '{"completion":"OK"}'])
def test_invalid_or_expired_response(document):
    with pytest.raises(GameError):
        parse_response(document)


@pytest.mark.parametrize("response", [{"question": "x", "step": "bad"}, {"question": "x", "progression": "nan"},
                                     {"id_proposition": "1", "name_proposition": ""}])
async def test_bad_state_does_not_overwrite_accepted_question(response):
    game = Game(Transport([response]))
    await game.start()
    question = game.state.question
    with pytest.raises(GameError):
        await game.answer(Answer.YES)
    assert game.state.question == question and game.state.question_number == 1


async def test_uncertain_answer_is_not_retried():
    transport = Transport([asyncio.TimeoutError()])
    game = Game(transport)
    await game.start()
    with pytest.raises(asyncio.TimeoutError):
        await game.answer(Answer.YES)
    assert [path for path, _ in transport.calls] == ["game", "answer"]
