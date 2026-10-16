# NoneBot Plugin Akinator

心里想一个人物，回答问题，让网络天才猜猜你想的是谁。

本仓库由 [LoCCai](https://github.com/LoCCai/nonebot-plugin-akinator) 接手维护，基于 LgCookie 的 MIT 插件。当前维护版本为 **1.1.2**，不代表 PyPI 已发布同版本。

## 安装

Python 3.10+、NoneBot 2.4.3+。从本维护仓库安装：

```bash
pip install 'nonebot-plugin-akinator @ git+https://github.com/LoCCai/nonebot-plugin-akinator.git'
```

需要图片卡片可安装 `[image]`，需要独立浏览器访问可安装 `[browser]`；`[all]` 包含两者。浏览器模式需要已有的 Playwright Chromium；首次安装环境可执行 `playwright install chromium`。插件不会自动安装、更新或改写浏览器及其他插件。

将模块加入 NoneBot 的加载配置：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_akinator"]
```

没有图片依赖时自动使用文字；没有七七私有函数库时使用插件自带实现。

## 使用

- `/aki`、`/akinator`、`/网络天才`、`/猜人物`：开始游戏。
- `/aki 帮助`：查看玩法。
- 回答 `1 是`、`2 否`、`3 不知道`、`4 可能是`、`5 可能不是` 中的序号或文字，也支持 Y/N/IDK/P/PN。
- `上一题` / `B`：撤销上一问；`退出` / `E`：结束。
- 出现猜测后：`是`确认猜中，`否`或`继续`接着猜。

只有发起者在原聊天中的回复有效，其他成员及其他 Bot 不会串局。无关聊天和其他命令会继续交给其他插件。默认两分钟未回答或整局超过二十分钟会释放会话。

## 配置

配置写入 Bot 的 `.env`，均为可选。

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `AKINATOR_CLIENT_TYPE` | `auto` | `httpx` / `playwright` / `auto`；自动模式仅在开局失败时尝试新浏览器会话 |
| `AKINATOR_LANGUAGE` | `cn` | 站点语言 |
| `AKINATOR_BASE_URL_TEMPLATE` | `https://{}.akinator.com` | `{}` 替换为语言；兼容原有代理站地址模板 |
| `AKINATOR_PROXY` | 空 | HTTP 与浏览器共同使用的代理；未设置时兼容原有 `PROXY` |
| `AKINATOR_CHILD_MODE` | `true` | 隐藏上游标记为不适宜的猜测结果 |
| `AKINATOR_TEXT_MODE` | `false` | 始终以文字展示 |
| `AKINATOR_OPERATION_TIMEOUT` | `120` | 等待一条回答的秒数 |
| `AKINATOR_REQUEST_TIMEOUT` | `20` | 网络请求秒数 |
| `AKINATOR_START_TIMEOUT` | `60` | 每种客户端开局尝试的总秒数 |
| `AKINATOR_SESSION_LIFETIME` | `1200` | 单局最大秒数 |
| `AKINATOR_MAX_SESSIONS` | `4` | 全进程最多同时保留的游戏（包括正在开局） |
| `AKINATOR_REQUEST_CONCURRENCY` | `2` | 上游操作最大并发 |
| `AKINATOR_ADMISSION_TIMEOUT` | `3` | 等待上游操作名额的秒数 |
| `AKINATOR_BROWSER_HEADLESS` | `true` | 独立游戏浏览器是否无界面 |
| `AKINATOR_VIRTUAL_DISPLAY` | `false` | Linux 有界面浏览器使用独立临时 Xvfb；需要机器已安装 Xvfb，无需 xauth |
| `AKINATOR_BROWSER_EXECUTABLE` | 空 | 使用已有 Chromium 的路径；空则按 Playwright 配置寻找 |
| `AKINATOR_HOST_INTEGRATION` | `true` | 自动检测七七发送、主题、截图和撤回函数；不存在或签名不兼容则使用内置实现 |
| `AKINATOR_RECALL_PREVIOUS` | `false` | 尝试撤回上一张题卡；失败不影响答题 |

网站可能拒绝某些网络或要求网页验证。当前部署测试中，现有代理站配合有界面 Chromium 可完成开局、答题及撤销；源站仍可能返回 403，插件不保证所有网络都能访问。Linux 服务器可按实际环境设置：

```dotenv
AKINATOR_CLIENT_TYPE=playwright
AKINATOR_BROWSER_HEADLESS=false
AKINATOR_VIRTUAL_DISPLAY=true
# AKINATOR_BROWSER_EXECUTABLE=/path/to/existing/chromium
```

不要继续使用旧版 `akinator-patch-import`：维护版已移除该工具，不再批量改写 Playwright，也不更改 htmlrender 的全局初始化或 `DISPLAY`。

## 七七集成与独立使用

菜单通过标准 `PluginMetadata.extra` 提供，归入“互动与游戏”，同时提供 QWeb 功能目录信息。无需依赖菜单插件即可正常玩游戏。

可选检测 `src.utils.message_fx`、`render_theme`、`bounded_htmlrender`、`onebot_recall`。这些模块不会列为安装依赖。发送开始后出现不确定结果时不会换通道重发；可选模块缺失时才选择内置发送。浏览器制图失败或超过 13 秒时，改用 Pillow 本地生成图片卡片，保留昼夜主题、题目、答案和猜测照片；本地制图需要系统已安装 Noto Sans CJK、文泉驿、苹方或微软雅黑。两种制图均不可用时才使用文字，保持当前题目，不重新提交答案。照片下载失败仅省略照片。答题计时在题卡生成后开始。

每局拥有自己的 Cookie、浏览器和显示进程；退出、超时、失败和插件关闭时清理。答题、撤销、继续和确认请求均不自动重试，避免一次回答被提交两次。

猜中后的 `/choice` 用于向上游记录结果。玩家回复“是”就正常结束并显示猜中；如果上游记录返回 500 或超时，后台保留未确认状态，不让统计接口故障打断已完成的游戏，也不重复提交。

自定义卡片 CSS 可放在 Bot 工作目录下 `data/akinator/additional.css`；已有 `data/akinator/akitude/*.png` 精灵图可继续使用。截图内容自包含，不等待远程字体或照片加载。

## 开发与验证

```bash
pip install -e . pytest pytest-asyncio
pytest -q
```

测试不连接 QQ、不访问真实 Akinator，覆盖新旧页面、可选签名、上游游标与题号、猜测确认和继续、儿童模式、请求失败、并发与清理，以及缺少七七依赖的加载。

## 致谢与许可

原插件作者 LgCookie；MIT 许可证见 [LICENSE](LICENSE)。新版协议适配参考 [akipy](https://github.com/advnpzn/akipy) 的 MIT 协议研究，许可全文见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。[Akinator-Bot](https://github.com/advnpzn/Akinator-Bot) 用作会话生命周期与操作边界的设计参考，未复制其无许可授权的源码。
