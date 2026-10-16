"""Akinator protocol state, independent of NoneBot and private host libraries.

Current/legacy field compatibility follows the MIT-licensed akipy protocol
research. See THIRD_PARTY_NOTICES.md. Credentials are never included in repr.
"""
from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass, field
from enum import IntEnum
from html.parser import HTMLParser
from typing import Any, Protocol


class GameError(RuntimeError):
    pass


class UpstreamBlocked(GameError):
    pass


class InvalidAction(GameError):
    pass


class Answer(IntEnum):
    YES = 0
    NO = 1
    I_DONT_KNOW = 2
    PROBABLY = 3
    PROBABLY_NOT = 4


class Transport(Protocol):
    async def start(self, fields: dict[str, str]) -> str: ...
    async def post(self, path: str, fields: dict[str, Any]) -> str: ...
    async def close(self) -> None: ...


class _PageFields(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inputs: dict[str, str] = {}
        self.texts: dict[str, str] = {}
        self.active: str | None = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        name = data.get("id") or data.get("name")
        if tag == "input" and name and data.get("value"):
            self.inputs[name] = data["value"]
        if tag == "p" and name in {"question-label", "p-sub-bubble"}:
            self.active, self.depth = name, 1
        elif self.active and tag not in {"br", "img", "input", "hr"}:
            self.depth += 1

    def handle_endtag(self, tag):
        if self.active:
            self.depth -= 1
            if self.depth <= 0:
                self.active = None

    def handle_data(self, text):
        if self.active:
            self.texts[self.active] = self.texts.get(self.active, "") + text


def parse_start(document: str) -> dict[str, Any]:
    parser = _PageFields()
    parser.feed(document)
    result: dict[str, Any] = {}
    for name in ("session", "signature", "identifiant", "step", "progression"):
        # Current pages use localStorage; older pages set hidden inputs in JS.
        patterns = (
            rf"localStorage\s*\.\s*setItem\(\s*['\"]{name}['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
            rf"\$\(\s*['\"]#{name}['\"]\s*\)\s*\.\s*val\(\s*['\"]([^'\"]+)['\"]\s*\)",
        )
        value = next((m[1] for p in patterns if (m := re.search(p, document))), None)
        result[name] = html.unescape(value or parser.inputs.get(name, "")) or None
    result["question"] = parser.texts.get("question-label", "").strip()
    if not result["session"] or not result["question"]:
        raise GameError("上游没有返回有效题目，请稍后重新开局。")
    try:
        result["step"] = int(result["step"] or 0)
        result["progression"] = float(result["progression"] or 0)
        if result["step"] < 0 or not math.isfinite(result["progression"]):
            raise ValueError
    except (ValueError, TypeError):
        raise GameError("上游返回的游戏状态无效，请重新开局。") from None
    return result


def parse_response(document: str, *, terminal=False) -> dict[str, Any]:
    try:
        value = json.loads(document)
    except (TypeError, ValueError):
        pre = re.search(r"<pre\b[^>]*>(.*?)</pre>", document, re.I | re.S)
        try:
            value = json.loads(html.unescape(pre[1])) if pre else None
        except ValueError:
            value = None
    if not isinstance(value, dict):
        raise GameError("上游返回了无法确认的结果，请重新开局。")
    completion = value.get("completion", "OK")
    if completion not in {"OK", "SOUNDLIKE"}:
        raise GameError("这局游戏已失效，请重新开局。")
    if completion != "SOUNDLIKE" and not ({"question", "id_proposition"} & value.keys()) and not (terminal and "step" in value):
        raise GameError("上游没有返回下一步结果，请重新开局。")
    return value


@dataclass
class Guess:
    id: str
    name: str
    description: str = ""
    photo: str = ""
    pseudo: str = ""
    flag_photo: str | int = ""


@dataclass
class GameState:
    session: str = field(default="", repr=False)
    signature: str | None = field(default=None, repr=False)
    identifiant: str | None = field(default=None, repr=False)
    question: str = ""
    step: int = 0
    progression: float = 0
    akitude: str = "defi.png"
    guess: Guess | None = None
    ended: bool = False
    no_question: bool = False
    last_proposition: str = ""
    child_blocked: bool = False
    answer_depth: int = 0
    confirmed: bool = False
    confirmation_recorded: bool = False
    confirmation_error_type: str = ""

    @property
    def question_number(self):
        # The upstream step cursor may increase even when undoing an answer.
        return self.answer_depth + 1


class Game:
    def __init__(self, transport: Transport, *, child_mode=False, theme=1):
        self.transport = transport
        self.child_mode = child_mode
        self.theme = theme
        self.state = GameState()
        self.started = False
        self.closed = False

    async def start(self):
        document = await self.transport.start({"sid": str(self.theme), "cm": str(self.child_mode).lower()})
        self.state = GameState(**parse_start(document))
        self.started = True
        return self.state

    def _fields(self):
        state = self.state
        if self.closed or not self.started or state.ended:
            raise InvalidAction("这局游戏已经结束，请重新开局。")
        fields = {"session": state.session, "step": str(state.step),
                  "progression": str(state.progression), "sid": str(self.theme),
                  "cm": str(self.child_mode).lower()}
        if state.signature:
            fields["signature"] = state.signature
        return fields

    def _update(self, data):
        state = self.state
        # Validate all conversions before changing the accepted local state.
        try:
            step = int(data.get("step", state.step))
            progression = float(data.get("progression", state.progression))
            if step < 0 or not math.isfinite(progression):
                raise ValueError
        except (ValueError, TypeError):
            raise GameError("上游返回的游戏状态无效，请重新开局。") from None
        if data.get("completion") == "SOUNDLIKE":
            state.ended, state.guess, state.akitude = True, None, "deception.png"
            return state
        guess = None
        if "id_proposition" in data:
            blocked = str(data.get("valide_contrainte", "1")) == "0"
            if blocked:
                state.child_blocked, state.ended, state.guess = True, True, None
                return state
            guess = Guess(str(data["id_proposition"]), html.unescape(str(data.get("name_proposition", ""))),
                          html.unescape(str(data.get("description_proposition", ""))),
                          str(data.get("photo") or ""), str(data.get("pseudo") or ""), data.get("flag_photo", ""))
            if not guess.name:
                raise GameError("上游的猜测结果不完整，请重新开局。")
        elif not str(data.get("question") or "").strip():
            raise GameError("上游的题目不完整，请重新开局。")
        state.step, state.progression, state.guess = step, progression, guess
        state.no_question = str(data.get("no_question", "0")) == "1"
        state.akitude = str(data.get("akitude") or ("confiant.png" if guess else "defi.png"))
        if guess:
            state.last_proposition = str(step)
        else:
            state.question = html.unescape(str(data["question"]))
        return state

    async def answer(self, answer: Answer):
        fields = self._fields()
        if self.state.guess:
            raise InvalidAction("已经有猜测结果了，请回复“是”或“继续”。")
        fields.update(answer=str(Answer(answer).value), step_last_proposition=self.state.last_proposition)
        state = self._update(parse_response(await self.transport.post("answer", fields)))
        state.answer_depth += 1
        return state

    async def back(self):
        fields = self._fields()
        if self.state.answer_depth <= 0:
            raise InvalidAction("已经是第一题啦。")
        state = self._update(parse_response(await self.transport.post("cancel_answer", fields)))
        state.answer_depth -= 1
        return state

    async def exclude(self):
        fields = self._fields()
        if not self.state.guess:
            raise InvalidAction("现在还没有猜测结果。")
        fields["forward_answer"] = "0" if self.state.no_question else "1"
        document = await self.transport.post("exclude", fields)
        if self.state.no_question:
            data = parse_response(document, terminal=True)
            if "step" not in data:
                raise GameError("上游未能确认继续游戏，请重新开局。")
            data["completion"] = "SOUNDLIKE"
        else:
            data = parse_response(document)
        return self._update(data)

    async def choose(self):
        fields = self._fields()
        guess = self.state.guess
        if not guess:
            raise InvalidAction("现在还没有猜测结果。")
        # The player's confirmation establishes the outcome. Upstream /choice
        # records statistics; its failure must not turn a correct guess into a
        # failed game or invite replaying the preceding answer.
        self.state.confirmed, self.state.ended, self.state.akitude = True, True, "triomphe.png"
        if not self.state.identifiant:
            self.state.confirmation_error_type = "MissingIdentifier"
            return self.state
        fields = {key: fields[key] for key in ("step", "sid", "session", "signature") if key in fields}
        fields.update(identifiant=self.state.identifiant, pid=guess.id, charac_name=guess.name,
                      charac_desc=guess.description, pflag_photo=guess.flag_photo)
        try:
            await self.transport.post("choice", fields)
        except Exception as exc:
            self.state.confirmation_error_type = type(exc).__name__
        else:
            self.state.confirmation_recorded = True
        return self.state

    async def close(self):
        if not self.closed:
            self.closed = True
            await self.transport.close()
