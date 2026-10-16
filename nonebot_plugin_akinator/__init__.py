from nonebot.plugin import PluginMetadata, inherit_supported_adapters, require

require("nonebot_plugin_waiter")
require("nonebot_plugin_alconna")

from .config import ConfigModel, config
from .const import HTML_RENDER_AVAILABLE

if HTML_RENDER_AVAILABLE and not config.akinator_text_mode:
    require("nonebot_plugin_htmlrender")

__version__ = "1.1.2"
MENU_GROUP = {"key": "games", "name": "互动与游戏",
              "description": "农场、修仙、面包店、抽取和群内互动玩法。", "sort_order": 70}
__plugin_meta__ = PluginMetadata(
    name="网络天才 Akinator",
    description="心里想一个人物，回答问题，让网络天才猜猜你想的是谁。",
    usage="/aki 开局；回复 1—5 或答案文字；上一题/退出；猜测后回复是、否或继续。/aki 帮助",
    homepage="https://github.com/LoCCai/nonebot-plugin-akinator",
    type="application", config=ConfigModel,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={
        "License": "MIT", "Author": "LgCookie, LoCCai", "version": __version__,
        "pmn": {"markdown": True, "sort_order": 170, "menu_group": MENU_GROUP},
        "qweb": {"catalog_provider": True, "key": "akinator", "slug": "akinator",
                 "audience": "群聊与私聊用户", "icon": "gamepad-2"},
        "menu_data": [{
            "func": "网络天才猜人物",
            "trigger_method": "命令：<命令前缀>aki / <命令前缀>网络天才",
            "trigger_condition": "群聊与私聊用户；仅本局发起者作答",
            "brief_des": "想好一个人物，回答问题，让网络天才来猜。",
            "detail_des": "回复 1—5 或答案文字；上一题可撤销，退出可结束。猜测后回复是确认，否或继续接着猜。",
            "pmn_hidden": False,
            "pmn_group": MENU_GROUP,
            "pmn_triggers": [{"type": "command", "label": "开始游戏", "value": "<命令前缀>aki"},
                             {"type": "command", "label": "游戏帮助", "value": "<命令前缀>aki 帮助"}],
            "qweb": {"key": "play", "slug": "play", "examples": [{"type": "command", "value": "aki"}]},
        }],
    },
)

# Metadata integrates with host menus; no host module is required to load.
from . import __main__ as __main__
