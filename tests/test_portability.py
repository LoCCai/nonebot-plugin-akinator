import asyncio
import importlib
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from akinator_core_test import integration
from akinator_core_test.game import GameState, Guess
from akinator_core_test.render import card_html


def test_missing_or_broken_private_modules_use_builtin_theme(monkeypatch):
    monkeypatch.setattr(importlib, "import_module", lambda _: (_ for _ in ()).throw(ModuleNotFoundError("no host")))
    assert integration.theme_context()["palette_mode"] == "day"
    assert integration.optional_callable("src.utils.anything", "x") is None


def test_incompatible_theme_helper_does_not_break_render(monkeypatch):
    monkeypatch.setattr(integration, "optional_callable", lambda *args: lambda required, extra: {})
    assert integration.theme_context()["theme"] == "day"


@pytest.mark.parametrize("mode", ["day", "night"])
def test_cards_escape_player_text_and_have_no_external_requests(mode):
    state = GameState(question='<script>alert("x")</script>')
    document = card_html(state, theme={"palette_mode": mode})
    assert "&lt;script&gt;" in document and '<script>alert' not in document
    assert "第 1 个问题" in document and "1</b> 是" in document
    assert 'src="http' not in document and 'url(http' not in document
    assert ('data-theme="dark"' in document) == (mode == "night")
    state.guess = Guess("1", "测试人物", "简介")
    document = card_html(state, theme={"palette_mode": mode})
    assert "测试人物" in document and "猜错了" in document


async def test_unknown_host_delivery_is_never_replayed(monkeypatch):
    class Message:
        def __init__(self, *args): pass
        async def export(self, **kwargs): return "exported"
        async def send(self, **kwargs): raise AssertionError("must not replay")
    monkeypatch.setitem(sys.modules, "nonebot_plugin_alconna.uniseg", types.SimpleNamespace(UniMessage=Message))
    helper = AsyncMock(side_effect=TimeoutError())
    monkeypatch.setattr(integration, "optional_callable", lambda *args: helper)
    bot = types.SimpleNamespace(adapter=types.SimpleNamespace(get_name=lambda: "OneBot V11"))
    event = types.SimpleNamespace()
    with pytest.raises(TimeoutError):
        await integration.send_message(bot, event, Message())
    assert helper.await_count == 1


async def test_absent_host_delivery_uses_native_send(monkeypatch):
    class Message:
        async def send(self, **kwargs): return "receipt"
    monkeypatch.setitem(sys.modules, "nonebot_plugin_alconna.uniseg", types.SimpleNamespace(UniMessage=Message))
    monkeypatch.setattr(integration, "optional_callable", lambda *args: None)
    bot = types.SimpleNamespace(adapter=types.SimpleNamespace(get_name=lambda: "test"))
    assert await integration.send_message(bot, object(), Message()) == ("native", "receipt")


async def test_recall_failure_is_contained():
    receipt = types.SimpleNamespace(recall=AsyncMock(side_effect=TimeoutError()))
    await integration.recall_message(object(), ("native", receipt), host=False)
    assert receipt.recall.await_count == 1


async def test_host_cards_render_local_html_without_navigating_to_a_placeholder_domain(monkeypatch):
    async def capture(document, **kwargs):
        # This is the host helper's navigation contract, not a separate preview
        # renderer that bypasses the optional integration path.
        assert kwargs['base_url'] == 'about:blank'
        assert '<main>' in document
        return b'card-image'
    helper = AsyncMock(side_effect=capture)
    monkeypatch.setattr(integration, 'optional_callable', lambda *args: helper)
    assert await integration.capture_html('<main>Question</main>') == b'card-image'
    assert helper.await_count == 1


def test_plugin_loads_without_private_host_or_image_runtime(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = '''
import importlib.abc, sys
import nonebot
class NoPrivateHost(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'src' or fullname.startswith('src.'):
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, NoPrivateHost())
nonebot.init(driver='~none', _env_file=None, akinator_text_mode=True)
sys.path.insert(0, sys.argv[1])
plugin = nonebot.load_plugin('nonebot_plugin_akinator')
assert plugin is not None
assert plugin.metadata.extra['menu_data'][0]['pmn_group']['key'] == 'games'
assert plugin.metadata.extra['pmn']['menu_group']['description']
assert plugin.metadata.extra['pmn']['menu_group'] == plugin.metadata.extra['menu_data'][0]['pmn_group']
assert isinstance(plugin.metadata.extra['pmn']['sort_order'], int)
assert plugin.metadata.homepage == 'https://github.com/LoCCai/nonebot-plugin-akinator'
from nonebot_plugin_akinator.config import config
assert config.akinator_text_mode
assert 'cooaki' not in sys.modules and 'fleep' not in sys.modules
assert not any(name == 'src' or name.startswith('src.') for name in sys.modules)
import asyncio
from nonebot_plugin_akinator import message, render
from nonebot_plugin_akinator.game import GameState
async def broken_render(*args, **kwargs):
    raise TimeoutError()
async def no_photo(*args):
    return None
render.render_card = broken_render
message.get_photo = no_photo
message.HTML_RENDER_AVAILABLE = True
config.akinator_text_mode = False
state = GameState(question='兼容性测试')
output = asyncio.run(message.build_message(state))
assert '兼容性测试' in str(output) and state.question_number == 1
async def working_render(*args, **kwargs):
    return b'card-image'
render.render_card = working_render
output = asyncio.run(message.build_message(state))
assert len(output) == 1 and output[0].type == 'image'
print('PORTABLE_PLUGIN_LOADED')
'''
    result = subprocess.run([sys.executable, "-c", script, str(root)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PORTABLE_PLUGIN_LOADED" in result.stdout
