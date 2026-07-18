---
name: cli
description: "终端 AI 编码代理 CLI 工具调用路由。记录各 CLI 工具（claude、opencode、codex、cursor-agent 等）的二进制名称、参数标志、调用方式，用于 Aries 子 Agent 任务委派路由。"
---

# CLI 工具调用路由 — 子 Agent 任务委派

## 概述

Aries 可以检测系统中已安装的终端 AI 编码代理 CLI 工具，并将子 Agent 任务委派给这些工具执行。本文档记录各 CLI 工具的正确调用方式，供 AI 在生成子 Agent 配置或路由决策时参考。

## 调用方式

每个 CLI 工具通过 `subprocess` 执行，参数路由由 `CLI_ROUTING_CONFIGS` 控制。核心调用模式：

```
<binary> <extra_args> <prompt_flag> <prompt>
```

### 会话连续性模式

| 模式 | 说明 |
|------|------|
| `separate` | 每次独立会话，通过 `--resume`/`--session` 维持上下文 |
| `history_only` | 历史作为文本重放到 prompt 中 |
| `none` | 无会话连续性，每次完全独立 |

---

## 各工具详情

### 1. Claude Code (`claude`)

| 属性 | 值 |
|------|----|
| **二进制** | `claude` |
| **非交互模式** | `-p` / `--print` |
| **prompt_flag** | `-p` |
| **extra_args** | `--dangerously-skip-permissions` |
| **conversation_mode** | `separate` |

**调用示例**：
```bash
claude -p "请帮我审查这段代码" --dangerously-skip-permissions
claude -p "重构 src/utils/index.ts" --model sonnet --dangerously-skip-permissions
```

**常用参数**：
- `--model <model>` — 指定模型（sonnet/opus 等）
- `-r, --resume [session_id]` — 恢复会话
- `-c, --continue` — 继续最近会话
- `--append-system-prompt <prompt>` — 追加系统提示
- `--permission-mode <mode>` — 权限模式（auto/bypassPermissions/default 等）
- `--output-format <format>` — 输出格式（text/json/stream-json）
- `--max-budget-usd <amount>` — 最大花费（仅 `--print` 模式）

---

### 2. OpenCode (`opencode`)

| 属性 | 值 |
|------|----|
| **二进制** | `opencode` |
| **非交互模式** | `opencode run [message..]` |
| **prompt_flag** | 空（位置参数） |
| **extra_args** | `run` |
| **conversation_mode** | `none` |

**调用示例**：
```bash
opencode run "帮我添加一个用户登录功能"
opencode run "修复这个 bug" --model claude-sonnet-4-20250514
```

**常用参数**：
- `--model <model>` — 指定模型（provider/model 格式）
- `-s, --session <id>` — 指定会话 ID
- `-c, --continue` — 继续上次会话
- `--prompt <prompt>` — 指定 prompt（替代位置参数）
- `--agent <agent>` — 指定 agent
- `--pure` — 不加载外部插件

---

### 3. Codex CLI (`codex`)

| 属性 | 值 |
|------|----|
| **二进制** | `codex` |
| **非交互模式** | `codex exec <prompt>` |
| **prompt_flag** | 空（位置参数） |
| **extra_args** | `exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --json` |
| **conversation_mode** | `history_only` |

**调用示例**：
```bash
codex exec "添加单元测试" --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox
codex exec "优化这段代码的性能" --model o3 --sandbox read-only
```

**常用参数**：
- `--model <model>` — 指定模型
- `-s, --sandbox <mode>` — 沙箱模式（read-only/workspace-write/danger-full-access）
- `-C, --cd <dir>` — 设置工作目录
- `-a, --ask-for-approval <policy>` — 审批策略
- `--search` — 启用联网搜索

---

### 4. Cursor Agent (`cursor-agent`)

| 属性 | 值 |
|------|----|
| **二进制** | `cursor-agent` / `agent` |
| **非交互模式** | `cursor-agent <prompt>` |
| **prompt_flag** | 空（位置参数） |
| **extra_args** | 无 |
| **conversation_mode** | `separate` |

**调用示例**：
```bash
cursor-agent "写一个 React 组件"
```

---

### 5. VS Code CLI (`code`)

| 属性 | 值 |
|------|----|
| **二进制** | `code` |
| **非交互模式** | `code --` |
| **prompt_flag** | 空 |
| **extra_args** | 无 |
| **conversation_mode** | `none` |

**用途**：启动 VS Code 编辑器，非编码代理，适合打开文件/目录。

**调用示例**：
```bash
code .                    # 打开当前目录
code --diff file1 file2   # 对比文件
code --wait src/index.ts  # 打开文件并等待关闭
```

---

### 6. Gemini CLI (`gemini`)

| 属性 | 值 |
|------|----|
| **二进制** | `gemini` |
| **prompt_flag** | 空（位置参数） |
| **extra_args** | `--code-only` |
| **conversation_mode** | `separate` |

---

### 7. Kimi Code (`kimi`)

| 属性 | 值 |
|------|----|
| **二进制** | `kimi` |
| **prompt_flag** | `-p` |
| **extra_args** | 无 |
| **conversation_mode** | `separate` |

---

### 8. CodeBuddy (`codebuddy`)

| 属性 | 值 |
|------|----|
| **二进制** | `codebuddy` / `cbc` |
| **prompt_flag** | `-p` |
| **extra_args** | 无 |
| **conversation_mode** | `separate` |

---

### 9. 其他工具

| 工具 | 二进制 | prompt_flag | extra_args | 会话模式 |
|------|--------|-------------|------------|----------|
| **MiMo Code** | `mimocode` / `mimo` | 空（位置参数） | `run` | `none` |
| **Trae CLI** | `traecli` / `trae` | 空（位置参数） | `run` | `none` |
| **Qoder CLI** | `qodercli` | 空（位置参数） | `--yolo` | `none` |

---

## 后端路由配置

当前路由配置定义在 `backend/utils/tools_status.py` 的 `CLI_ROUTING_CONFIGS` 字典中。如需新增或修改，编辑该文件后重启后端即可。

```python
CLI_ROUTING_CONFIGS = {
    "claude": {
        "prompt_flag": "-p",
        "extra_args": ["--dangerously-skip-permissions"],
        "conversation_mode": "separate",
    },
    "opencode": {
        "prompt_flag": "",
        "extra_args": ["run"],
        "conversation_mode": "none",
    },
    "codex": {
        "prompt_flag": "",
        "extra_args": ["exec", "--skip-git-repo-check"],
        "conversation_mode": "history_only",
    },
    # ... 更多工具
}
```

## 子 Agent 配置示例

用户在设置子 Agent 时，可以指定 `agent_type` 为对应 CLI 工具的 ID，AI 将根据此 skill 中记录的调用方式路由任务。

### 示例：创建一个 Claude Code 子 Agent

```
agent_type: claude
model: sonnet
prompt: 你是一个代码审查专家，请审查以下代码变更
```

### 示例：创建一个 OpenCode 子 Agent

```
agent_type: opencode
prompt: 你是一个前端开发专家，请实现以下功能
```

当子 Agent 被触发时，Aries 后端会根据 `agent_type` 查找对应的路由配置，组装命令行并执行。
