---
name: computer-use
description: "控制 Windows 桌面。截图只是兜底，优先永远是 CLI 命令和 Playwright 浏览器自动化。四层优先级：CLI > Playwright > 窗口命令 > 截图视觉。"
---

# Computer Use — Windows 桌面控制

通过 Win32 API 控制鼠标、键盘、截图和窗口管理。所有操作基于 `ctypes`（标准库），零额外依赖。

## AI 执行指令（必须遵守）

**截图只是兜底，优先永远是 CLI 命令和 Playwright 浏览器自动化。**

执行任何桌面任务时，严格按以下四层优先级决策，从第 1 层开始尝试，走不通才降级：

### 四层优先级

| 优先级 | 方式 | 说明 | 适用场景 |
|--------|------|------|----------|
| **1（最高）** | **CLI 命令** | `subprocess` 直接执行命令行 | 打开应用、执行系统命令、文件操作 |
| **2** | **Playwright 浏览器** | DOM 快照 + 元素 ref 点击 | 浏览器内操作（网页、Web 应用） |
| **3** | **窗口命令** | `computer_window` / `computer_keyboard` | 窗口管理、快捷键、文本输入 |
| **4（兜底）** | **截图视觉** | `computer_screenshot` + `computer_mouse` | 只有前三层都走不通时，才截图定位坐标 |

### 决策流程

1. **先思考**：分析目标，拆解步骤
2. **第 1 层 CLI**：能用命令行完成的，直接执行（如 `start notepad`、`start msedge https://...`）
3. **第 2 层 Playwright**：浏览器内操作，用 DOM 快照 + ref 点击，不依赖视觉
4. **第 3 层窗口命令**：`computer_window` 打开/聚焦窗口、`computer_keyboard` 输入文本或按快捷键
5. **第 4 层截图兜底**：只有前三层都走不通、且需要知道屏幕上某个元素的具体坐标时，才截图
6. **最小截图**：不要每一步都截图。只在「需要定位坐标」和「需要验证结果」两个节点截图

### 找应用的策略

- **打开桌面应用前，先用 `list_files` 确认桌面是否有对应快捷方式**：
  - 例如：`list_files(subdir="C:\\Users\\<用户名>\\Desktop", pattern="*WeChat*")`
  - 如果桌面上有 `微信.lnk` 或 `WeChat.lnk`，再用 `computer_window(action="open", app="微信")` 打开
- **桌面没有时，用 `computer_window(action="open", app="...")` 走系统启动**：它会依次尝试 `os.startfile`、`cmd /c start`、搜索桌面、PowerShell，总耗时最多 6 秒
- **命令也打不开时，用搜索框搜索**：按 `Win` 键打开开始菜单搜索，或用 `Win+S` 打开搜索
- **搜索也找不到时，才截图在桌面上找图标**

### 反例（错误做法）

❌ 每做一步就截图 —— 浪费 token，效率低
❌ 用猜测的固定坐标点击 —— 容易点错窗口
❌ 明明可以用命令打开应用，还先截图找图标
❌ 浏览器内操作不用 Playwright，而用截图点击

### 正例（正确做法）

✅ 打开微信前先确认桌面：`list_files(subdir="C:\\Users\\<用户名>\\Desktop", pattern="*WeChat*")`
✅ 桌面有微信快捷方式：`computer_window(action="open", app="微信")`（CLI，无需截图）
✅ 聚焦豆包：`computer_window(action="focus", title="豆包")`（窗口命令，无需截图）
✅ 输入文字：`computer_keyboard(action="type", text="你好", method="sendinput")`（窗口命令，无需截图）
✅ 浏览器搜索：用 Playwright `snapshot` + `click e26`（DOM 操作，无需截图）
✅ 点击桌面图标：先 `computer_screenshot()`，再用归一化坐标 `computer_mouse(action="click", x=0.5, y=0.3, normalized=True)`

### 示例：给豆包发送"你好"

推荐流程（CLI > 窗口命令 > 截图兜底）：

```
# 1. 先确认桌面是否有豆包快捷方式（list_files 工具，非 computer_use）
list_files(subdir="C:\\Users\\<用户名>\\Desktop", pattern="*豆包*")

# 2. CLI 打开豆包（第 1 层，无需截图）
computer_window(action="open", app="豆包")

# 2. 窗口命令聚焦豆包窗口（第 3 层，无需截图）
computer_window(action="focus", title="豆包")

# 3. 截图，定位输入框坐标（第 4 层兜底，仅此步骤需要视觉）
computer_screenshot()
# → 返回 width, height 和 base64 图片
# → 从图片中估算输入框的归一化坐标 (0~1 范围)

# 4. 点击输入框（归一化坐标，不受分辨率影响）
computer_mouse(action="click", x=0.5, y=0.9, normalized=True)

# 5. 输入文本（窗口命令，无需截图）
computer_keyboard(action="type", text="你好", method="sendinput")

# 6. 按回车发送（窗口命令，无需截图）
computer_keyboard(action="press", keys=["enter"])

# 7. 可选：截图确认消息已发送
computer_screenshot()
```

## 可用工具

| 工具 | 说明 |
|------|------|
| `computer_screenshot` | 截屏（全屏 / 指定区域 / 指定显示器），仅在需要视觉定位时调用（第 4 层兜底） |
| `computer_mouse` | 鼠标操作。支持归一化坐标 (`normalized=True`, 0~1) 和物理像素坐标 |
| `computer_keyboard` | 键盘操作。输入文本 / 按键 / 组合键 |
| `computer_window` | 窗口管理。列表 / 聚焦 / 关闭 / 最小化 / 最大化 / 启动应用 |

## 工作流详解

### 1. 窗口管理（优先使用命令）

```
# 启动应用
computer_window(action="open", app="notepad")
computer_window(action="open", app="msedge https://www.baidu.com")
computer_window(action="open", app="豆包")

# 聚焦已有窗口
computer_window(action="focus", title="豆包")

# 关闭窗口
computer_window(action="close", title="记事本")
```

### 2. 键盘操作

```
# 输入文本（支持中文，默认 auto 模式）
computer_keyboard(action="type", text="你好世界")

# 豆包、微信等应用推荐 sendinput 模式
computer_keyboard(action="type", text="你好", method="sendinput")

# 剪贴板粘贴模式（部分传统应用需要）
computer_keyboard(action="type", text="你好", method="clipboard")

# 按单个键
computer_keyboard(action="press", keys=["enter"])
computer_keyboard(action="press", keys=["escape"])

# 组合键
computer_keyboard(action="hotkey", keys=["ctrl", "c"])
computer_keyboard(action="hotkey", keys=["alt", "tab"])
computer_keyboard(action="hotkey", keys=["win", "d"])
```

**输入方式说明**：

| method | 说明 | 适用场景 |
|--------|------|----------|
| `auto`（默认） | ASCII 用 keybd_event，非 ASCII 用 SendInput Unicode | 大多数应用 |
| `sendinput` | 全部字符用 SendInput Unicode 直接发送 | 豆包、微信等 |
| `clipboard` | 剪贴板 + Ctrl+V 粘贴 | 部分传统应用 |

### 3. 鼠标操作（坐标优先用归一化）

```
# 点击：推荐用归一化坐标 (0~1)，不受分辨率影响
computer_mouse(action="click", x=0.5, y=0.9, normalized=True)

# 也支持物理像素坐标（默认）
computer_mouse(action="click", x=960, y=980)

# 双击
computer_mouse(action="double_click", x=0.5, y=0.9, normalized=True)

# 右键
computer_mouse(action="right_click", x=0.5, y=0.3, normalized=True)

# 滚轮
computer_mouse(action="scroll", scroll_direction="down", scroll_amount=3)

# 拖拽（归一化）
computer_mouse(action="drag", x=0.1, y=0.1, end_x=0.4, end_y=0.3, normalized=True)
```

**重要**：
- **推荐用归一化坐标** (`normalized=True`)：x/y 为 0~1 的百分比，不受分辨率影响，借鉴 UI-TARS 方案
- 点击前必须先调用 `computer_screenshot()` 获取当前画面
- 截图返回的 `width` 和 `height` 用于参考，归一化坐标自动转换为物理像素
- 也支持物理像素坐标（`normalized=False`，默认），与截图 1:1 对应

### 4. 截图（视觉兜底）

```
# 仅在需要定位坐标或验证结果时截图
computer_screenshot()

# 指定显示器
computer_screenshot(monitor=1)
```

## 坐标系统

- **归一化坐标**（推荐，`normalized=True`）：x/y 为 0~1 的百分比，借鉴 UI-TARS 方案，不受分辨率/DPI 影响
- **物理像素坐标**（默认，`normalized=False`）：与截图 1:1 对应
- 已启用 DPI 感知，高分辨率屏幕下物理像素坐标不会被缩放
- 截图全屏时返回的 `width` 和 `height` 即为屏幕物理分辨率

## 支持的按键名称

| 类别 | 键名 |
|------|------|
| 字母 | a-z |
| 数字 | 0-9 |
| 功能键 | f1-f24 |
| 修饰键 | ctrl, alt, shift, win |
| 编辑 | enter, tab, escape, backspace, delete, insert, home, end, pageup, pagedown, space |
| 方向 | up, down, left, right |
| 锁定 | capslock, numlock, scrolllock |
| 其他 | printscreen, pause |

## 注意事项

1. **四层优先级** — CLI > Playwright > 窗口命令 > 截图兜底，截图是最后手段
2. **点击前必须截图** — 鼠标坐标必须来自最新 screenshot，严禁猜测坐标
3. **归一化坐标优先** — 截图兜底时推荐 `normalized=True`，用 0~1 百分比定位
4. **中文输入** — 豆包等应用推荐 `method="sendinput"`，不要用默认 auto
5. **组合键顺序** — keys 列表中前面的键先按下，后面的后按下，释放顺序相反
6. **窗口标题** — 精确匹配优先，其次是开头匹配，最后是包含匹配
7. **找应用策略** — 桌面应用优先 CLI 打开，找不到用搜索框搜索，最后才截图找图标
8. **截图保存** — 截图保存到 `~/.Aries/tmp/computer_screenshots/`

## ESC 强制中断

当 AI 正在执行 computer-use 操作时，**按下键盘 ESC 键**可随时强制中断 AI 执行：

- ESC 监听在检测到 computer-use 工具调用时自动启动
- 按下 ESC 后，AI 当前轮次执行完毕即停止，不会继续下一轮
- 中断后已有进度会保存到数据库，用户可发送"继续"恢复
- ESC 监听在会话结束（正常结束/中断/报错）后自动停止
