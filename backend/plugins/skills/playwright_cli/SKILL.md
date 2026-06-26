---
name: playwright-cli
description: "通过 playwright-cli 控制浏览器：网页抓取、截图/PDF、DOM 快照、JS 执行、元素点击。复用会话 aries + profile ~/.Aries/browser_profile 保持登录态。适用于网页自动化、登录态操作、表单交互、在线答题等场景。当用户需要浏览器操作、网页截图、页面内容提取、自动化点击时使用此技能。"
---

# Playwright 浏览器自动化

通过 `playwright-cli` 命令行工具控制浏览器。所有操作通过 `scripts/playwright.py` 脚本封装，自动管理会话和登录态。

## 环境准备

### 安装 playwright-cli

```bash
npm install -g playwright-cli
npx playwright install chromium
```

### 验证安装

```bash
playwright-cli --version
python scripts/playwright.py status
```

## 核心概念

- **会话（Session）**：默认 `aries`，通过 `--session` 参数自定义
- **Profile**：`~/.Aries/browser_profile/`，保存登录态和 Cookie，自动复用
- **Temp 目录**：`~/.Aries/tmp/`，命令行生成的快照文件等临时数据存放在此
- **headless / headed**：默认 headed（显示窗口）；需登录时必须 headed

## 脚本用法速查

| 命令 | 说明 | 示例 |
|------|------|------|
| `open` | 打开浏览器 | `python scripts/playwright.py open "https://example.com"` |
| `snapshot` | DOM 快照（含 ref） | `python scripts/playwright.py snapshot` |
| `click` | 点击元素 | `python scripts/playwright.py click e26` |
| `eval` | 执行 JS | `python scripts/playwright.py eval "document.title"` |
| `scrape` | 提取文本 | `python scripts/playwright.py scrape --selector ".content"` |
| `screenshot` | 截图 | `python scripts/playwright.py screenshot` |
| `pdf` | 导出 PDF | `python scripts/playwright.py pdf` |
| `dismiss-dialog` | 关闭弹窗 | `python scripts/playwright.py dismiss-dialog` |
| `close` | 关闭浏览器 | `python scripts/playwright.py close` |
| `status` | 查看会话状态 | `python scripts/playwright.py status` |
| `batch_click` | 批量点击 | `python scripts/batch_click.py e26 e45 e76` |
| `batch_fill` | 批量填入输入框 | `python scripts/batch_fill.py e45:答案1 e60:答案2` |

## 核心规则（违反会导致失败）

1. **同页多步：只有 `open` 带 URL**，后续 `snapshot`/`click`/`eval` 不带 URL
2. **`click` 前必须先 `snapshot`**，获取 ref（如 `e26`），ref 随页面变化会失效
3. **登录态自动复用**：profile 目录 `~/.Aries/browser_profile/`，首次需 headed 手动登录
4. **eval 表达式**：`document.title` ✅；`var x=1` ❌（会自动包 IIFE）
5. **遇 modal state 错误**：先 `dismiss-dialog`，再重试

## 标准工作流

### 1. 首次打开页面（唯一需要 URL 的一步）

```bash
python scripts/playwright.py open "https://example.com"
```

等待页面加载后，获取快照：

```bash
python scripts/playwright.py snapshot
```

### 2. 同页操作（不需要 URL）

```bash
# 点击元素（ref 从 snapshot 获取）
python scripts/playwright.py click e26

# 执行 JS
python scripts/playwright.py eval "document.title"

# 再次快照验证
python scripts/playwright.py snapshot
```

### 3. 截图与 PDF

```bash
python scripts/playwright.py screenshot
python scripts/playwright.py pdf
```

### 4. 提取页面内容

```bash
# 提取整页文本
python scripts/playwright.py scrape

# 提取指定元素
python scripts/playwright.py scrape --selector ".article-content"
```

### 5. 关闭浏览器

```bash
python scripts/playwright.py close
```

Profile 内登录态保留；下次 `open` 仍登录。

## 批量操作

### 批量点击

```bash
python scripts/batch_click.py e26 e45 e76
# 或逗号分隔
python scripts/batch_click.py e26,e45,e76
# 自定义间隔
python scripts/batch_click.py e26 e45 --delay 500
```

### 批量填入输入框

传入 `ref:内容` 列表，逐个填入。ref 从 snapshot 获取。自动识别元素类型：INPUT/TEXTAREA 用 `value`；富文本编辑器（contenteditable / iframe body，如 UEditor）用 `innerHTML`。中文内容不会被转义。

```bash
# 空格分隔
python scripts/batch_fill.py e45:答案1 e60:答案2 e78:答案3
# 逗号分隔
python scripts/batch_fill.py e45:答案1,e60:答案2
# 自定义间隔
python scripts/batch_fill.py e45:答案1 e60:答案2 --delay 500
```

填入富文本编辑器（如 UEditor）时，先 snapshot 找到 iframe body 的 ref，再填入，内容会被包在 `<p>` 标签内：

```bash
python scripts/batch_fill.py e120:这是富文本内容
```

## 何时用 headed

- 需登录的网站 / 用户要看浏览器 / 做题点选 → `open` 默认 headed
- 纯后台抓取正文 → `open --headless`

## 常见错误排查

| 现象 | 原因 | 处理 |
|------|------|------|
| click 超时 | ref 过期（页面变过） | 重新 snapshot 再 click |
| eval SyntaxError | 用了 `var` 语句 | 改成表达式 |
| 看到登录页 | profile 无 cookie | `open` 不加 `--headless`，手动登录一次 |
| `modal state` 错误 | 页面有 alert/confirm 弹层 | 先 `dismiss-dialog` |
| 提示没有打开的会话 | 浏览器未启动或已关闭 | 先 `open` 打开页面 |
| 中文变成 `\uXXXX` | `json.dumps` 默认转义非 ASCII | 脚本已用 `ensure_ascii=False` 修复 |
| PowerShell `&&` 报错 | PowerShell 不支持 `&&` | 用 `;` 分隔命令 |
| batch_fill 返回 unsupported | 元素非 INPUT/TEXTAREA 且非 contenteditable | 检查 ref 是否指向输入框或编辑器 |

## 底层命令（调试用）

```bash
playwright-cli list
playwright-cli -s=aries open --headed --persistent --profile ~/.Aries/browser_profile <url>
playwright-cli -s=aries goto <url>
playwright-cli -s=aries snapshot
playwright-cli -s=aries click e26
playwright-cli -s=aries close
```

## 附加资源

- 超星学习通 DOM 与错误排查：[reference.md](reference.md)
- 工具调用示例：[examples.md](examples.md)
- 批量点击：[scripts/batch_click.md](scripts/batch_click.md)
