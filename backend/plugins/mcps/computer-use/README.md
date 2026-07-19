# computer-use-mcp-server

一个 MCP（Model Context Protocol）server，把 OpenAI Codex 的 `codex-computer-use.exe`
（即 @oai/sky 的 Windows GUI 自动化后端）暴露成一组标准 MCP 工具。

**任何支持 MCP 且带视觉能力的 agent**（Claude Desktop、Cursor、各类 MCP client、
本仓库里的 Aries 智能体等）都可以直接驱动本地 Windows GUI--无需自己实现
JSON-RPC 握手、无需关心 x-oai-cua-approved-app 的自动批准流程。

---

## 它做了什么

| 能力 | 说明 |
|------|------|
| 应用 / 窗口发现 | 枚举已安装应用、运行中窗口，返回 `{app, id}` 句柄 |
| 窗口快照 | 截图（以 MCP image content block 返回，视觉模型直接可见）+ 无障碍树（UI 元素索引） |
| 语义操作 | 按**元素索引**精确点击、设置值、输入文本、按键、滚动、拖拽、次级无障碍动作 |
| 自动批准 | 后端要求对敏感操作做 app 批准时，client 自动尝试常见 app 标识，无需人工确认 |

截图数据流：`get_window_state` -> 后端返回 `screenshots[].url` 形式的 `data:image/jpeg;base64,...`
data URL -> server 解析出 base64 放进 MCP `image` content block -> 视觉模型看到屏幕。

---

## 目录结构

本插件随 Aries 源码打包在 `backend/plugins/mcps/computer-use/`，启动时由 `plugin_manager`
自动同步到用户目录 `~/.Aries/plugins/mcps/computer-use/`（含 `codex-computer-use.exe`）。

```
~/.Aries/plugins/mcps/computer-use/   # 释放后的运行目录
├── codex-computer-use.exe            # GUI 自动化后端二进制（随插件同步）
├── index.mjs                         # MCP server 入口（注册工具、调用 client）
├── src/sky_client.js                 # JSON-RPC 客户端（spawn exe、协议、自动批准）
├── package.json
└── node_modules/                     # 依赖随插件一并同步，开箱即用
```

`sky_client.js` 会按优先级搜索多个候选位置查找 `codex-computer-use.exe`
（插件根目录 → 上两级 → `~/.Aries/plugins/mcps/computer-use/`）；也可用 `COMPUTER_USE_EXE`
环境变量显式覆盖路径。

---

## 运行前置条件

- Windows 10/11
- Node.js >= 18
- `codex-computer-use.exe` 与 `node_modules` 均随插件自动释放到 `~/.Aries/plugins/mcps/computer-use/`
  （可用 `COMPUTER_USE_EXE` 环境变量覆盖 exe 路径）

---

## 启动 server（stdio 传输）

```bash
cd ~/.Aries/plugins/mcps/computer-use
node index.mjs
```

server 以 stdio 方式运行，等待 MCP client 通过标准输入输出连接。
正常启动后不会有任何控制台输出（日志走 stderr，带 `[computer-use]` 前缀）。

---

## 接入任意 MCP + 视觉 agent

只要 agent 支持 stdio 型 MCP server，把下面这条命令配置进去即可。

> 路径说明：Aries 启动时会自动把本插件（含 `codex-computer-use.exe`、`index.mjs`、`src/` 等）
> 从源码同步到用户目录 `~/.Aries/plugins/mcps/computer-use/`。因此配置中直接使用释放后的路径即可，
> 无需关心项目源码位置。Windows 下推荐用正斜杠 `/` 避免转义。

### 通用配置（JSON）

```json
{
  "mcpServers": {
    "computer-use": {
      "command": "node",
      "args": [
        "C:/Users/Lenovo/.Aries/plugins/mcps/computer-use/index.mjs"
      ],
      "env": {
        "COMPUTER_USE_IDLE_MS": "120000"
      }
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "computer-use": {
      "command": "node",
      "args": [
        "C:/Users/Lenovo/.Aries/plugins/mcps/computer-use/index.mjs"
      ],
      "env": {
        "COMPUTER_USE_IDLE_MS": "120000"
      }
    }
  }
}
```

### Cursor / VS Code（`.cursor/mcp.json` 或 `mcp.json`）

```json
{
  "mcpServers": {
    "computer-use": {
      "command": "node",
      "args": [
        "C:/Users/Lenovo/.Aries/plugins/mcps/computer-use/index.mjs"
      ],
      "env": {
        "COMPUTER_USE_IDLE_MS": "120000"
      }
    }
  }
}
```

> 注意：
> - agent 自身必须具备视觉能力，否则即使 server 返回了 image block，
>   模型也无法"看"到截图。无障碍树（文本）始终会随截图一起返回，可作为无视觉时的降级线索。
> - `codex-computer-use.exe` 与 `node_modules` 均随插件自动释放，无需手动安装依赖。

---

## 工具列表

| 工具 | 入参 | 作用 |
|------|------|------|
| `list_apps` | - | 列出已安装应用 + 窗口 |
| `list_windows` | - | 列出当前可操作窗口（返回 `{app, id}` 列表） |
| `get_window` | `id`, `app?` | 用 id 重新获取窗口对象 |
| `launch_app` | `appId` | 启动应用（app id 或 .exe 路径） |
| `activate_window` | `app`, `id` | 窗口置前 |
| `get_window_state` | `app`, `id`, `includeScreenshot=true`, `includeText=true` | **核心感知工具**：截图 + 无障碍树 |
| `click` | `app`, `id`, `elementIndex?`, `x?`, `y?`, `clickCount?`, `mouseButton?`, `screenshotId?` | 点击（优先元素索引，降级坐标） |
| `type_text` | `app`, `id`, `text` | 输入文本（支持中文） |
| `set_value` | `app`, `id`, `elementIndex`, `value` | 直接设值（表单字段更可靠） |
| `press_key` | `app`, `id`, `key` | 按键/组合键，如 `Return`、`Control_L+a` |
| `scroll` | `app`, `id`, `x`, `y`, `scrollX?`, `scrollY?`, `screenshotId?` | 滚动 |
| `drag` | `app`, `id`, `fromX`, `fromY`, `toX`, `toY`, `screenshotId?` | 拖拽 |
| `perform_secondary_action` | `app`, `id`, `action`, `elementIndex` | 次级无障碍动作（Scroll Up/Down、Expand、Collapse…） |

---

## 典型使用循环（agent 内部）

1. `list_windows` 找到目标窗口（`{app, id}`）
2. `get_window_state(includeScreenshot=true, includeText=true)` 获取截图 + 元素树
3. 从无障碍树里读元素索引 -> `click(elementIndex=N)` / `set_value(...)` / `type_text(...)`
4. 若元素不可用，才用截图坐标做坐标点击（`click(x, y, screenshotId)`）
5. 操作后再 `get_window_state` 确认结果

> 提示：后端要求任何窗口输入操作前，本会话内至少调用过一次 `get_window_state`
> （用于建立屏幕快照上下文）。agent 按上面的循环做即可自然满足。

---

## 控制层生命周期（重要）

`codex-computer-use.exe` 会在屏幕上显示控制样式（高亮/闪光）。Cursor 等宿主会**常驻**本 MCP server，若不主动关闭 exe，控制层会一直挂着。

本 server 的策略：

1. **懒启动**：首次调用任意工具时才 spawn exe
2. **空闲自动释放**：距上次工具调用超过 `COMPUTER_USE_IDLE_MS`（默认 **15000** ms）后，自动 `close` exe，撤掉控制层
3. **显式释放**：可调用工具 `release` 立即关闭
4. **进程退出**：SIGINT / SIGTERM / stdin 断开时也会关闭

在 `mcp.json` 里可调整空闲时间：

```json
"computer-use": {
  "command": "node",
  "args": [
    "C:/Users/Lenovo/.Aries/plugins/mcps/computer-use/index.mjs"
  ],
  "env": {
    "COMPUTER_USE_IDLE_MS": "15000"
  }
}
```

修改代码后需在 Cursor 里 **Reload MCP**（或重启 Cursor），新逻辑才会生效。

---

## 协议细节（供好奇者）

- 客户端 spawn `codex-computer-use.exe --parent-pid <pid>`
- 每行一条 JSON：`{id, method, params, meta?}`，响应同样单行 JSON
- 后端返回 `approvalRequest` 时，client 用候选 app 标识补 `meta.x-oai-cua-approved-app`
  后重发，直到被接受（或候选耗尽报错）
- 完整协议记录在 `src/sky_client.js` 的头部注释中
