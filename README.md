# Aries

[![Release](https://github.com/xiaoxiaoy51s/Aries/actions/workflows/release.yml/badge.svg)](https://github.com/xiaoxiaoy51s/Aries/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

本地 AI 编程助手桌面应用。基于 Electron + Vue 3 前端与 Python FastAPI 后端，支持多模型对话、工具调用、终端、Skills / MCP、子 Agent 等能力。

开源仓库：**[github.com/xiaoxiaoy51s/Aries](https://github.com/xiaoxiaoy51s/Aries)**

---

## 环境要求

| 依赖 | 版本建议 |
|------|----------|
| Node.js | 18+ |
| Python | 3.11+ |
| Git | 可选 |

Windows 为主要开发/运行平台，macOS / Linux 让ai帮忙检测一下，没有跨平台的功能。

---

## 快速启动（开发）

需要 **先构建后端 CLI**，再启动后端与前端。

### 1. 构建后端 CLI（终端 / 命令执行依赖）

后端会通过 Node.js 启动 `backend/cli` 服务，用于内置终端、Shell 命令等。首次克隆或修改 CLI 代码后需执行：
npm install容易拉取不下来，最好使用代理运行
```bash
cd backend/cli
npm install
npm run build
```

编译产物在 `backend/cli/dist/`。未 build 时后端会尝试用 `tsx` 直接跑 TypeScript，但 **推荐始终先 `npm run build`**。

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
python main.py
```

后端默认监听 `http://127.0.0.1:30000`，健康检查：`GET /health`。启动时会自动拉起 CLI 服务。

### 3. 启动前端

**方式 A — Electron 桌面（推荐）**

```bash
cd frontend
npm install
npm run electron:dev
```

会自动启动 Vite（`5173`）并打开 Electron 窗口；开发模式下 Electron 会尝试用 `python main.py` 拉起后端（若后端已在运行则复用）。

**方式 B — 仅浏览器**

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`（需确保后端已在 30000 端口运行）。

---

## 打包发布

### 本地打包

```bash
# 1. 后端 CLI
cd backend/cli && npm install && npm run build

# 2. 后端 exe（Windows）
cd backend
pip install -r requirements.txt pyinstaller
pyinstaller aries.spec --noconfirm
mkdir ../frontend/resources 2>nul
copy dist\aries.exe ..\frontend\resources\aries_backend.exe

# 3. Electron 安装包
cd ../frontend
npm install
npm run electron:build
```

安装包输出在 `frontend/release/`。`aries_backend.exe` 由 CI 构建，不提交到 Git。

### GitHub Actions 自动发布

仓库：**[github.com/xiaoxiaoy51s/Aries](https://github.com/xiaoxiaoy51s/Aries)**

推送版本 tag 后自动构建 Windows 安装包并创建 Release：

```bash
git tag v1.0.0
git push origin v1.0.0
```

也可在 GitHub **Actions → Release → Run workflow** 手动触发。

Release 资产包含 NSIS 安装包、`latest.json`（检测更新）等。发布前请将 `frontend/package.json` 的 `version` 与 tag 一致。

---

## 目录结构

```
.
├── backend/          # FastAPI 后端、Agent 引擎、工具与 MCP
│   └── cli/          # Node.js CLI 服务（终端 / PTY，需 npm run build）
├── frontend/         # Vue 3 + Electron 桌面客户端
│   ├── electron/     # 主进程
│   ├── src/          # 渲染进程 UI
│   └── resources/    # 打包用后端 exe 等资源
└── README.md
```

用户数据与配置默认保存在 **`~/.Aries/`**（会话日志、模型配置、Skills、MCP 等）。

---

## 功能概览

- **多模型对话** — 接入 OpenAI 兼容 API，支持流式回复、深度思考展示、Token / 上下文占用
- **Agent 工具** — 读写文件、终端命令、Git、Todo、子 Agent 委派等
- **工作区** — 文件浏览、Monaco 编辑、Diff 预览、内置终端（多 Tab）
- **Skills & MCP** — 可扩展技能与 MCP 服务器
- **自动化** — 定时任务与多平台 Bot（飞书 / 微信等，按需配置）
- **桌面宠物** — 可选的桌面小助手动画
- **设置中心** — 模型、账号、路径权限、网络代理、开发环境等

---

## 常见问题

**端口被占用**

后端端口可通过环境变量修改：

```bash
set BACKEND_PORT=30001
python main.py
```

**Electron 找不到后端**

开发模式下请确认已安装 Python 且 `backend/main.py` 可正常启动；或手动先启动后端再运行 `npm run electron:dev`。

**终端 / 命令工具不可用**

确认已执行 `cd backend/cli && npm install && npm run build`，且本机已安装 Node.js 18+。

**首次使用**

在「设置 → 模型管理」中配置 API Base URL 与模型后再开始对话。

---

## License

[MIT](LICENSE)
