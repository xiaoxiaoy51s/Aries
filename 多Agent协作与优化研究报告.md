# 多 Agent 协作与优化研究报告

> 研究对象：MIMOClaw 后端多 Agent 架构
> 参考标杆：Claude Code 官方实现（claude-code-main 源码 + 官方文档）
> 日期：2026-06-22

---

## 目录

1. [研究背景与方法](#一研究背景与方法)
2. [Claude Code 官方多 Agent 架构剖析](#二claude-code-官方多-agent-架构剖析)
3. [MIMOClaw 后端现状分析](#三mimoclaw-后端现状分析)
4. [关键差距对比](#四关键差距对比)
5. [优化建议与实施路线](#五优化建议与实施路线)
6. [附录](#六附录)

---

## 一、研究背景与方法

### 1.1 研究目标

MIMOClaw 后端已实现一套基于配置驱动的单层多 Agent 系统，但存在并行委派名不副实、子 Agent 上下文缺失等已知缺口。本研究旨在：

- 深入理解 Claude Code 官方的多 Agent 协作模式（Coordinator Mode、Fork Subagent、Sub-Agent 机制）
- 对照 MIMOClaw 后端现状，识别关键差距
- 提出可落地的优化建议与实施路线

### 1.2 研究材料

| 材料 | 来源 | 用途 |
|------|------|------|
| `frontend/agent.md` | VSCode 官方 Explore agent 标准 | 子 Agent 设计范式参考 |
| Claude Code 官方文档（7 篇） | ccb.agent-aura.top | 官方多 Agent 机制权威说明 |
| `claude-code-main` 源码 | 本地代码库 | 官方实现的插件/Agent 实例分析 |
| `backend/` 代码 | 本地代码库 | MIMOClaw 现状分析 |

### 1.3 研究方法

- 并行抓取 7 篇官方文档（Coordinator Mode、Fork Subagent、Sub-Agents、Worktree 隔离、Coordinator 与 Swarm、TeamMem、Daemon）
- 使用探索子 Agent 深度分析 claude-code-main 源码中的 Agent 插件实现
- 使用探索子 Agent 彻底分析 backend 的 subagent_manager / subagent_runtime / agent_mode
- 综合三方材料，对照差距，产出优化建议

---

## 二、Claude Code 官方多 Agent 架构剖析

Claude Code 的多 Agent 体系由四个核心概念构成，它们有清晰的边界和适用场景。

### 2.1 四类执行路径

| 类型 | 触发方式 | 是否经过 Tool 协议 | 结果回注方式 | 典型入口 |
|------|----------|-------------------|-------------|---------|
| **命名子 Agent** | 模型调用 `Agent({subagent_type: "..."})` | 是 | 当前 turn 的 `tool_result` 或后台 `<task-notification>` | AgentTool |
| **AgentTool Fork** | 模型调用 `Agent({})`（省略 subagent_type，fork gate 开启） | 是 | 先返回 `async_launched`，完成后任务通知 | forkSubagent.ts |
| **Slash Command Fork** | 用户执行 `context: fork` 的命令 | 否 | 同步命令输出或后台隐藏 prompt | processSlashCommand |
| **runForkedAgent()** | 运行时内部服务分叉 | 否 | 调用方内部消费 | forkedAgent.ts |

**一句话记忆**：AgentTool fork 是给模型用的工具语义；runForkedAgent() 是给运行时内部用的实现细节；slash command fork 是命令/技能的执行模式。

### 2.2 Coordinator Mode（编排者模式）

**核心思想**：将 CLI 变为"编排者"角色，编排者不直接操作文件，而是通过 AgentTool 派发任务给多个 worker 并行执行。

**关键约束**：
- 编排者只能使用三个工具：`Agent`（派发 worker）、`SendMessage`（继续 worker）、`TaskStop`（停止 worker）
- Worker 拥有完整工具集（Bash、Read、Edit 等）+ MCP + Skill
- 编排者的每条消息都是给用户看的；worker 结果以 `<task-notification>` XML 形式到达

**典型工作流**：
```
用户: "修复 auth 模块的 null pointer"

编排者:
 1. 并行派发两个 worker:
    - Agent({ description: "调查 auth bug", prompt: "..." })
    - Agent({ description: "研究 auth 测试", prompt: "..." })
 2. 收到 <task-notification>:
    - Worker A: "在 validate.ts:42 发现 null pointer"
    - Worker B: "测试覆盖情况..."
 3. 综合发现，继续 Worker A:
    - SendMessage({ to: "agent-a1b", message: "修复 validate.ts:42..." })
 4. 收到修复结果，派发验证:
    - Agent({ description: "验证修复", prompt: "..." })
```

**六大关键设计决策**：

| 决策 | 说明 | 启示 |
|------|------|------|
| 双开关设计 | feature flag 控制代码可用性，环境变量控制实际激活 | 允许编译时包含但不默认启用，降低部署风险 |
| 编排者受限 | 只能用 Agent/SendMessage/TaskStop | 确保编排者专注派发而非执行 |
| Worker 不可见编排者对话 | 每个 worker 的 prompt 必须自包含 | 避免上下文泄露，保证 worker 独立性 |
| 并行优先 | 系统提示强调"Parallelism is your superpower" | 鼓励并行派发独立任务 |
| 综合而非转发 | 编排者必须理解 worker 发现，再写出具体指令 | 禁止 "based on your findings" 类懒惰委托 |
| Scratchpad 可选共享 | 通过 GrowthBook 门控的共享目录 | 让 worker 之间持久化共享知识 |

### 2.3 Fork Subagent（上下文继承子 Agent）

**核心思想**：让 AgentTool 生成"fork 子 agent"，继承父级完整对话上下文。子 agent 看到父级的所有历史消息、工具集和系统提示。

**四大核心优势**：
1. **Prompt Cache 最大化**：多个并行 fork 共享相同的 API 请求前缀，只有最后的 directive 文本块不同
2. **上下文完整性**：子 agent 继承父级的完整对话历史（包括 thinking config）
3. **权限冒泡**：子 agent 的权限提示上浮到父级终端显示
4. **Worktree 隔离**：支持 git worktree 隔离，子 agent 在独立分支工作

**Fork 与普通 Agent 的对比**：

| 维度 | 普通 Agent | Fork Agent |
|------|-----------|------------|
| 上下文 | 从零开始 | 继承父级完整历史 |
| 工具集 | 按 agent definition 过滤 | 使用父级 exact tools（`useExactTools: true`） |
| System Prompt | 重新渲染 | 直传 `renderedSystemPrompt` |
| 权限模式 | 重新组装（默认 acceptEdits） | `bubble`（冒泡到父级） |
| Thinking config | 默认禁用 | 继承父级 |
| Cache 友好度 | 低（前缀不一致） | 高（前缀完全一致） |

**Prompt Cache 优化策略**（fork 设计的核心目标）：

| 优化点 | 实现 |
|--------|------|
| 相同 system prompt | 直传 `renderedSystemPrompt`，避免重新渲染 |
| 相同工具集 | `useExactTools: true` 直接使用父级工具 |
| 相同 thinking config | 继承父级 thinking 配置 |
| 相同占位符结果 | 所有 fork 使用 `FORK_PLACEHOLDER_RESULT` 相同文本 |
| ContentReplacementState 克隆 | 默认克隆父级替换状态，保持 wire prefix 一致 |

**递归防护**（两层检查防止 fork 嵌套）：
1. `querySource` 检查：`toolUseContext.options.querySource === 'agent:builtin:fork'`
2. 消息扫描：`isInForkChild()` 扫描消息历史中的 `<fork-boilerplate>` 标签

### 2.4 Sub-Agent 机制总览

**AgentTool 主流程**：
```
assistant message
 -> tool_use: Agent({ prompt, subagent_type?, run_in_background?, ... })
 -> query.ts: runTools(...)
 -> toolExecution.ts: await tool.call(...)
 -> AgentTool.call(...)
 -> resolve selectedAgent / fork path / permission mode / tool pool
 -> runAgent(...)
 -> finalizeAgentTool(...)
 -> mapToolResultToToolResultBlockParam(...)
 -> user message with tool_result
 -> query.ts starts next model turn
```

**路由规则**：
```
subagent_type 有值      → 使用命名 agent
subagent_type 省略 + fork 开启 → 使用 fork agent
subagent_type 省略 + fork 关闭 → 回退到 general-purpose
```

**三层权限模型**：

| 层级 | 检查内容 | 说明 |
|------|---------|------|
| 启动权限 | `filterDeniedAgents()` / `requiredMcpServers` / teammate 限制 / fork 递归保护 | 能否启动这个 agent |
| 工具池权限 | `assembleToolPool()` + `resolveAgentTools()` | 这个 agent 有哪些工具 |
| 执行权限 | acceptEdits / default / bypassPermissions / bubble | 工具执行时如何处理权限请求 |

**同步 vs 异步子 Agent**：

| 特性 | 同步子 Agent | 异步子 Agent |
|------|-------------|-------------|
| 触发 | 默认路径（无 `run_in_background`） | `run_in_background: true` 或 `background: true` 或 coordinator/fork 强制 |
| 等待 | 外层 `await tool.call(...)` 阻塞 | 返回 `async_launched`，通过 `<task-notification>` 回注 |
| 可后台化 | 支持（前台 iterator 可被清理，新后台 iterator 接管） | 原生异步 |
| 结果聚合 | 当前 turn 的 `tool_result` | 统一任务通知队列 |

**完成通知与统一队列**：异步子 Agent 完成后，结果通过 `<task-notification>` XML 消息进入统一队列。队列在主 Agent 空闲（无工具调用、无流式输出）时消费。

**继续通信工具**：
- `SendMessage({ to: "agent-id", message: "..." })`：继续已存在的 Worker
- `TaskOutput({ task_id: "..." })`：获取后台 agent 输出
- `TaskStop({ task_id: "..." })`：停止运行中的 Worker

### 2.5 Worktree 隔离（Git Worktree 文件级隔离）

**核心思想**：多 Agent 并行工作时，共享同一工作目录会导致写入冲突、状态干扰、不可区分三类问题。Git worktree 在同一仓库中创建多个独立工作目录，每个在自己的分支上。

**目录结构与命名规则**：
```
<repo-root>/
├── .claude/worktrees/
│   ├── fix-auth-bug/          # worktree 工作目录
│   │   ├── .git               # 指向主仓库的链接文件
│   │   └── src/...            # 独立的文件系统视图
│   └── add-dark-mode/         # 另一个 worktree
├── src/                       # 主工作目录（不受影响）
└── .git/                      # 主仓库
```
分支命名规则为 `worktree/<slug>`，slug 由 `validateWorktreeSlug()` 校验（只允许字母、数字、`.`、`_`、`-`，总长 ≤64 字符）。

**创建流程**（`EnterWorktreeTool`）：
1. 检查是否已在 worktree 中（防嵌套）
2. 解析到主仓库根目录
3. 生成 slug
4. `createWorktreeForSession()` — **Hook 优先**：检查 `WorktreeCreate` hook，有则执行 hook 命令（支持非 git VCS），无则走 git 原生路径
5. **快速恢复路径**：如果目标路径已存在，直接读取 `.git` 指针文件获取 HEAD SHA（纯文件 I/O，无子进程），跳过 `fetch` + `worktree add` 流程，将恢复延迟降到接近 0
6. 更新进程状态：`process.chdir(worktreePath)` + 持久化到项目配置 + 清空系统提示和 memory 缓存

**退出流程**（`ExitWorktreeTool`）两种策略：

| 策略 | 行为 |
|------|------|
| `keep` | chdir 回 originalCwd，worktree 目录和分支保留在磁盘上，用户可后续手动合并 |
| `remove` | **fail-closed 设计**：先 `countWorktreeChanges()` 统计未提交文件和新提交，有变更则拒绝（除非 `discard_changes: true`），git 失败时返回 `null` 假设不安全 |

**与 Agent 工具的联动**：

| 维度 | 用户会话 worktree | 子 Agent worktree |
|------|------------------|-------------------|
| 调用者 | EnterWorktreeTool | AgentTool |
| Session 管理 | 设置 `currentWorktreeSession` | **不设置** |
| 恢复已有 worktree | 直接复用 | 复用并 bump mtime（防误删） |
| 清理方式 | ExitWorktreeTool | `cleanupWorktreeIfNeeded()` 自动：有变更保留、无变更删除 |

**Session 状态持久化**：`WorktreeSession` 对象持久化到磁盘，包含 originalCwd、worktreePath、worktreeBranch、originalHeadCommit、sessionId 等，使得 `--resume` 时能正确还原 worktree 上下文。

**Sparse Checkout 优化**：对于大型 monorepo，支持 `sparsePaths` 配置只检出特定目录，在 210K 文件仓库中将创建时间从数十秒降到几秒。

### 2.6 协调者与蜂群模式（Coordinator vs Swarm）

Claude Code 有两种多 Agent 拓扑，控制权和状态模型完全不同。

**五层系统分层**：

| 层 | 回答的问题 | 典型对象 |
|----|-----------|---------|
| 入口层 | 用户/模型通过什么工具启动动作 | `/coordinator`、AgentTool、TeamCreate、SendMessage、TaskUpdate |
| 编排层 | 谁负责拆解、派发、控制和综合 | Coordinator、Team Lead、AgentTool routing |
| 运行层 | 谁真正执行或代表执行状态 | LocalAgentTask、InProcessTeammateTask、RemoteAgentTask |
| 通信层 | 结果和控制信号如何回流 | tool_result、`<task-notification>`、mailbox、CCR events |
| 持久化层 | 进程重启后还能看见什么 | session JSONL、sidechain、team config、task files、inbox、sidecar meta |

**两种拓扑对比**：

| 维度 | Coordinator Mode | Agent Teams / Swarm |
|------|-----------------|---------------------|
| 拓扑 | 星型：Coordinator 居中，worker 外围 | 团队型：Team Lead + named teammates + mailbox + task list |
| 主 Claude 角色 | 只编排，不直接执行 | 可以直接执行，也可作为 team lead 管理团队 |
| 执行者 | built-in `worker` async subagent | teammate（in-process 或 pane-based） |
| 通信方式 | `<task-notification>` + `SendMessage(to: agentId)` | mailbox by name，支持 P2P、broadcast、structured protocol |
| 任务协作 | 不以 TeamCreate/TaskList 为核心 | TeamFile + shared task list + mailbox |
| 恢复模型 | mode 在主 transcript，worker 是 local agent sidechain | team/task/inbox 文件可保留；in-process runner 不完整恢复 |

**何时用哪套机制**：

| 场景 | 推荐机制 | 原因 |
|------|---------|------|
| 需要主脑拆解、派发、综合、纠偏 | Coordinator Mode | 主线程被限制为编排器，减少直接上手乱改 |
| 多任务相对独立，需要长期队友持续领任务 | Swarm | 有 team config、mailbox、shared task list |
| 只想派一个专家研究或修改 | 普通 subagent | 成本低、路径短、结果直接回当前 turn |
| 想复制当前上下文做并行探索 | fork agent | 继承父上下文和 exact tools |
| 想把工作放到远端环境执行 | remote agent | 本地只保留镜像，执行在 CCR |

**Swarm 存储拓扑**：
```
~/.claude/
  teams/<team-name>/
    config.json              # TeamFile：name、leadAgentId、members[]
    inboxes/<agent-name>.json  # mailbox：按 name 寻址，非 agentId
  tasks/<team-name>/
    .highwatermark
    1.json, 2.json, ...     # 共享任务白板
```

**Mailbox 协议**（不只是"聊天"）：

| 限制 | 值 |
|------|-----|
| 单条 text | 64KB |
| mailbox 文件 | 4MB |
| retained bytes | 2MB |
| 普通 message 保留 | 最多 1000 条 |
| read message 保留 | 最多 200 条 |
| unread protocol message 保留 | 最多 2000 条 |

协议消息类型包括：plain text、broadcast、`task_assignment`、permission、plan、shutdown、mode 等，保持 unread 给 poller 路由。

**in-process vs pane-based teammate**：

| 维度 | in-process teammate | pane-based teammate |
|------|--------------------|--------------------|
| 运行位置 | leader 同进程 | 独立终端 pane / CLI 进程 |
| 消息消费 | runner 约 500ms poll mailbox | leader/teammate 约 1s poll |
| 恢复 | 内存状态，进程重启不能完整恢复 | pane 进程可能还在；恢复是 best-effort |

**AgentTool 五条分流路径**：同一 `Agent` 工具根据参数走不同运行时 —— teammate（有 name+team）、remote（isolation:remote）、fork（省略 subagent_type）、async local、sync local。

### 2.7 TeamMem（团队共享记忆）

**核心思想**：基于 GitHub 仓库的团队共享记忆系统，`memory/team/` 目录中的文件双向同步到 Anthropic 服务器，团队所有认证成员可共享项目知识。

**六大核心特性**：
- **增量同步**：只上传内容哈希变化的文件（delta upload）
- **冲突解决**：基于 ETag 的乐观锁 + 412 冲突重试
- **密钥扫描**：上传前检测并跳过包含密钥的文件
- **路径穿越防护**：所有写入路径验证在 `memory/team/` 边界内
- **分批上传**：自动拆分超过 200KB 的 PUT 请求避免网关拒绝
- **文件监视**：watcher 检测变更自动 push，抑制 pull 写入引起的假变更

**同步策略**：Server-wins on pull（服务端覆盖本地），Local-wins on push（本地覆盖服务端）—— 本地用户正在编辑不应被静默丢弃。

**Push 流程**：
1. 递归扫描 `memory/team/`，跳过超大文件（>250KB）
2. 密钥扫描（gitleaks 规则），检测到密钥跳过该文件
3. 计算 delta = 本地文件 - serverChecksums（只含哈希不同的文件）
4. `batchDeltaByBytes()` 拆分为 ≤200KB 批次
5. 逐批 upload，200 成功更新 checksums，412 冲突刷新重试（最多 2 次），413 超容量学习 serverMaxEntries

**API 端点**：
```
GET /api/claude_code/team_memory?repo={owner/repo}             → 完整数据 + checksums
GET /api/claude_code/team_memory?repo={owner/repo}&view=hashes → 仅 checksums（冲突解决用）
PUT /api/claude_code/team_memory?repo={owner/repo}             → 上传 entries（upsert 语义）
```

### 2.8 Daemon（后台守护进程）

**核心思想**：将 Claude Code 变为后台守护进程。主进程（supervisor）管理多个 worker 子进程的生命周期，通过文件系统状态文件进行通信。适用于持续运行的后台服务场景。

**架构**：
```
Supervisor (daemonMain)
  │
  ├── Worker: remoteControl
  │    └── runBridgeHeadless() — 远程控制 headless 模式
  │        接收远程会话、处理消息、权限审批
  │
  ▼
文件系统状态文件 (daemon-state.json)
  - PID、CWD、启动时间、Worker 类型
  - queryDaemonStatus() / stopDaemonByPid()
```

**Worker 生命周期管理**：

| 机制 | 说明 |
|------|------|
| 指数退避重启 | 初始 2s，上限 120s，倍数 ×2 |
| 快速失败检测 | 10s 内连续崩溃 5 次则 parking（不再重启） |
| 永久错误退出码 | 78 (EXIT_CODE_PERMANENT) 导致直接 parking |
| 优雅关闭 | SIGTERM/SIGINT → abort signal → 30s 强制 SIGKILL |

**CLI 入口**：
```
claude daemon start              # 启动守护进程
claude daemon status / ps        # 查看状态
claude daemon stop               # 停止
claude --daemon-worker=remoteControl  # 以 worker 身份启动
claude daemon bg                 # 后台会话管理
claude daemon attach <session>   # 附加会话
```

**关键设计决策**：
1. **多进程架构**：一个 supervisor + 多个 worker，进程隔离
2. **文件系统状态通信**：通过 `daemon-state.json` 文件共享状态（非 Unix 域套接字）
3. **与 BRIDGE_MODE 强绑定**：双重门控，两个 feature 都需开启
4. **Worker 环境变量**：supervisor 通过 `DAEMON_WORKER_*` 环境变量向 worker 传递配置

### 2.9 Claude Code 源码中的 Agent 实例分析

claude-code-main 代码库包含 15 个预定义 Agent，分布在 5 个插件中：

| 插件 | Agent 数量 | 代表 Agent |
|------|-----------|-----------|
| feature-dev | 3 | code-explorer, code-architect, code-reviewer |
| pr-review-toolkit | 6 | code-reviewer, code-simplifier, comment-analyzer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer |
| plugin-dev | 3 | agent-creator, plugin-validator, skill-reviewer |
| hookify | 1 | conversation-analyzer |
| agent-sdk-dev | 2 | agent-sdk-verifier-py, agent-sdk-verifier-ts |

**Agent 定义 Schema**（YAML frontmatter）：
```markdown
---
name: code-reviewer          # 必填，小写字母/数字/连字符，3-50字符
description: Use this agent when...  # 必填，含 <example> 块定义触发条件
model: sonnet                # inherit / sonnet / opus / haiku
color: blue                  # blue/cyan/green/yellow/magenta/red
tools: ["Read", "Grep"]      # 可选，省略则全部工具
---

[系统提示词 - Markdown 正文]
```

**模型选择策略**（来自 code-review 插件）：
- **haiku**：简单判断任务（PR 是否关闭/草稿、文件列表收集）
- **sonnet**：中等复杂度（PR 摘要、CLAUDE.md 合规审查、架构分析）
- **opus**：高复杂度（bug 检测、逻辑分析、问题验证、代码简化）

**工具集配置模式**：
- 只读分析：`["Read", "Grep", "Glob"]`
- 代码生成：`["Read", "Write", "Grep"]`
- 测试执行：`["Read", "Bash", "Grep"]`
- 全部访问：省略 `tools` 字段

**并行编排模式**（feature-dev 插件的 7 阶段工作流）：
- Phase 2：并行启动 2-3 个 code-explorer Agent（不同关注点）
- Phase 4：并行启动 2-3 个 code-architect Agent（不同架构方案）
- Phase 6：并行启动 3 个 code-reviewer Agent（不同审查焦点）

**结果聚合模式**：
```
# PR Review Summary
## Critical Issues (X found)
- [agent-name]: Issue description [file:line]
## Important Issues (X found)
## Suggestions (X found)
## Strengths
```

**多阶段验证流水线**（code-review 插件的 9 步流水线）：
1. 步骤 1-3：顺序预处理（haiku 检查 PR 状态 → haiku 收集文件 → sonnet 生成摘要）
2. 步骤 4：并行审查（4 个 Agent：2 sonnet + 2 opus，不同焦点）
3. 步骤 5：并行验证（为每个发现启动子 Agent 验证）
4. 步骤 6-9：过滤与输出

**置信度过滤**：每个问题附带 0-100 的置信度评分，只报告 >= 80 的问题，减少误报。

---

## 三、MIMOClaw 后端现状分析

### 3.1 整体架构

MIMOClaw 后端采用 **"主 Agent 作为编排者"（Main-Agent-as-Orchestrator）** 模式，没有独立的编排器组件。主 Agent 通过 LLM 自主决策何时、如何委派任务给子 Agent。

**核心模块**：

| 模块 | 文件 | 职责 |
|------|------|------|
| 子 Agent 配置管理 | [subagent_manager.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_manager.py) | 加载/保存/校验子 Agent 配置 |
| 子 Agent 执行引擎 | [subagent_runtime.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py) | 运行子 Agent 的多轮工具循环 |
| 子 Agent CRUD API | [subagents.py](file:///d:/agent/MIMOClaw/backend/api/subagents.py) | 前端管理接口 + 运行时取消 |
| 能力注册表 | [capability_registry.py](file:///d:/agent/MIMOClaw/backend/utils/capability_registry.py) | 统一检索 skill/mcp/subagent |
| 主 Agent 模式 | [agent_mode.py](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py) | 主 Agent 流式执行 + 委派分支 |

### 3.2 子 Agent 生成流程

1. **主 Agent system prompt 注入路由表**：[agent_mode.py:315-336](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py#L315-L336) 调用 `build_subagent_router_section()`，将所有可用子 Agent 以精简格式拼入 system prompt
2. **主 Agent 调用 `delegate_to_subagent` 工具**：定义在 [capability_registry.py:259-303](file:///d:/agent/MIMOClaw/backend/utils/capability_registry.py#L259-L303)
3. **主 Agent 循环拦截委派**：[agent_mode.py:679-773](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py#L679-L773)，当 `tool_name == "delegate_to_subagent"` 时进入异步执行分支
4. **工具集组装**：[subagent_runtime.py:397-412](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py#L397-L412)

### 3.3 执行模型：同步阻塞 + 流式状态推送

`run_subagent()` 是 **同步阻塞** 调用 —— 主 Agent 一直等到子 Agent 完成才返回。期间通过 `on_event` 回调持续推送状态事件（`subagent_event` / `subagent_reasoning` / `subagent_content` / `subagent_tool_call` / `subagent_tool_result`）。

主 Agent 在 [agent_mode.py:708-729](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py#L708-L729) 通过 `asyncio.create_task` 启动子 Agent，并用 `asyncio.Queue` + `_drain_subagent_events()` 在等待期间持续向前端 SSE 推送事件。

### 3.4 结果回传机制

子 Agent **必须** 调用 `report_to_main` 工具（[subagent_runtime.py:109-136](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py#L109-L136)）提交结果：

```
成功: {"result": "<final_output>", "log_path": "..."}
失败: {"error": "...", "status": "failed|timeout|cancelled", "log_path": "..."}
```

关键约束：如果子 Agent 输出纯文本而**未调用** `report_to_main`，视为**失败**。

### 3.5 三道防线超时

| 防线 | 超时值 | 说明 |
|------|--------|------|
| LLM 读取超时 | 900 秒 | 单轮 LLM 流式响应无数据 |
| 单工具超时 | 600 秒 | 单个工具执行 |
| 总超时 | 1800 秒（30 分钟） | 子 Agent 整体硬上限 |
| 空闲告警 | 60 秒 | 标记 stalled（仅提示，不杀任务） |
| 最大轮数 | 15 轮 | `SUBAGENT_MAX_ROUNDS` |

### 3.6 上下文隔离

子 Agent 拥有**完全独立**的上下文窗口：
- 子 Agent 的 `messages` 列表只包含：一条 system prompt + 一条 user task
- 子 Agent **看不到**主 Agent 与用户的对话历史
- 子 Agent 的 system prompt 由 `_build_subagent_system_prompt()` 构造，包含身份声明、用户配置的 system_prompt、任务通信规则、Skills 上下文、主 Agent 提供的 context、本次 task

### 3.7 防递归机制

子 Agent 调用以下工具会被拦截（[subagent_runtime.py:757-806](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py#L757-L806)）：
- `delegate_to_subagent`（禁止子 Agent 再委派）
- `capability_search`（禁止子 Agent 搜索能力全集）

**架构是单层委托，不支持层级嵌套。**

---

## 四、关键差距对比

### 4.1 架构层面差距

| 维度 | Claude Code 官方 | MIMOClaw 后端 | 差距 |
|------|-----------------|--------------|------|
| **并行执行** | 原生支持并行派发，"Parallelism is your superpower" | 系统提示承诺并发但实现为串行（`for tc in tool_calls_buffer` 逐个 await） | **严重** |
| **委派层级** | 支持多 Agent 类型 + Fork 继承上下文 | 单层委托，显式禁止嵌套 | 中等 |
| **编排器** | 独立的 Coordinator Mode（受限工具集）+ Swarm 团队模式 | 隐式编排（LLM 驱动，无独立组件） | 中等 |
| **任务分解** | 命令文件结构化分解（feature-dev 7 阶段） | 完全依赖 LLM 判断 | 中等 |
| **结果聚合** | 结构化聚合（Critical/Important/Suggestions/Strengths） | LLM 自行综合 | 中等 |
| **继续通信** | SendMessage/TaskOutput/TaskStop 三工具 | 无（子 Agent 一次性返回） | 中等 |
| **文件级隔离** | Git Worktree 隔离（per-agent 独立分支） | 无隔离，共享工作目录 | **严重** |
| **后台守护** | Daemon 多进程架构（supervisor + worker） | 无后台守护进程 | 中等 |
| **多 Agent 拓扑** | 星型 Coordinator + 团队型 Swarm 两种 | 仅隐式编排一种 | 中等 |

### 4.2 上下文/记忆差距

| 维度 | Claude Code 官方 | MIMOClaw 后端 | 差距 |
|------|-----------------|--------------|------|
| **Fork 上下文继承** | Fork 子 Agent 继承父级完整对话历史 | 无 Fork 机制，子 Agent 从零开始 | **严重** |
| **Prompt Cache 优化** | Fork 共享相同请求前缀，最大化 cache 命中 | 无 cache 优化考虑 | 中等 |
| **子 Agent 项目记忆** | Agent 可声明 `memory: project` 作用域 | 子 Agent 不获得主 Agent 的 agent.md / rules.md | **严重** |
| **编码行为约束** | Agent 定义包含完整行为规则 | CODING_BEHAVIOR_RULES 只注入主 Agent | 中等 |
| **共享工作空间** | Scratchpad 可选共享目录 + TeamMem 团队共享记忆 | 唯一通道是 task（入）和 report_to_main.message（出，限 500 字） | **严重** |
| **团队共享记忆** | TeamMem 基于 GitHub 仓库双向同步 | 无团队记忆共享机制 | 中等 |
| **Mailbox 通信** | Swarm mailbox 按 name 寻址，支持 P2P/broadcast/protocol | 无 mailbox，仅 report_to_main 单向 | 中等 |

### 4.3 执行层面差距

| 维度 | Claude Code 官方 | MIMOClaw 后端 | 差距 |
|------|-----------------|--------------|------|
| **同步/异步** | 同步可后台化 + 原生异步 + 统一任务通知队列 | 仅同步阻塞（伪异步：asyncio.create_task 但仍 await） | **严重** |
| **模型分层** | haiku/sonnet/opus 按任务复杂度选择 | 子 Agent 配置固定 model + fallback | 中等 |
| **置信度过滤** | 问题附带 0-100 置信度，只报告 >= 80 | 无置信度机制 | 低 |
| **重试/恢复** | 任务可恢复（resumeAgent.ts） | 无重试/恢复机制 | 中等 |
| **能力检索** | 无语义检索（文档未提及） | 关键词匹配（无 embedding） | 低 |
| **最大轮数** | 可配置（maxTurns） | 固定 15 轮 | 低 |

### 4.4 最严重的三个差距

**差距 1：并行委派名不副实**

系统提示词明确告诉主 Agent（[agent_mode.py:265](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py#L265)）：
> "同一轮 tool_calls 中可以并发委派多个不同 Subagent"

但实际实现是串行的（[agent_mode.py:662](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py#L662)）：
```python
for tc in tool_calls_buffer:
    ...
    if tool_name == "delegate_to_subagent":
        sub_task_obj = asyncio.create_task(run_subagent(...))
        while not sub_task_obj.done():
            await asyncio.wait_for(asyncio.shield(sub_task_obj), timeout=0.5)
            ...
        sub_result = await sub_task_obj  # 阻塞等待完成
        ...
        continue  # 下一个 tool_call
```

即使主 Agent 在同一轮返回了多个 `delegate_to_subagent` 的 tool_calls，它们也会被**逐个串行执行**。代码中也没有使用 `asyncio.gather` 或 `asyncio.as_completed`。

**差距 2：子 Agent 缺少项目记忆与编码约束**

子 Agent 的 system prompt 构造（[subagent_runtime.py:236-266](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py#L236-L266)）**不调用** `build_agent_memory_system_section()`，因此子 Agent 看不到主 Agent 的项目记忆（agent.md）和用户规则（rules.md）。同时 `CODING_BEHAVIOR_RULES` 也只注入主 Agent。

这导致子 Agent 缺少项目代码结构、开发命令、编码约定的上下文，可能产生与项目约定不一致的代码。

**差距 3：无 Fork 机制导致上下文浪费**

Claude Code 的 Fork 机制让子 Agent 继承父级完整上下文，并通过共享请求前缀最大化 Prompt Cache 命中率。MIMOClaw 的子 Agent 每次从零开始，无法利用已有的对话上下文，既浪费 token 又降低响应质量。

---

## 五、优化建议与实施路线

### 5.1 优先级 P0：实现真正的并行委派

**问题**：系统提示承诺并发但实现为串行。

**方案**：将 `delegate_to_subagent` 的 tool_calls 批量并发执行。

**实施位置**：[agent_mode.py:662](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py#L662) 的 `for tc in tool_calls_buffer` 循环。

**改造思路**：
```python
# 1. 先分离 delegate_to_subagent 调用和其他工具调用
delegate_calls = [tc for tc in tool_calls_buffer if tc.function.name == "delegate_to_subagent"]
other_calls = [tc for tc in tool_calls_buffer if tc.function.name != "delegate_to_subagent"]

# 2. 其他工具串行执行
for tc in other_calls:
    result = await execute_tool(tc)
    ...

# 3. delegate_to_subagent 并行执行
if delegate_calls:
    tasks = [run_subagent(parse_args(tc)) for tc in delegate_calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 4. 收集结果，按 tool_call_id 回注
```

**注意事项**：
- 需要为每个子 Agent 维护独立的 `asyncio.Queue` 推送 SSE 事件
- 需要处理部分失败（某个子 Agent 异常不应影响其他）
- 需要限制最大并发数（建议 3-5 个），防止资源耗尽

### 5.2 优先级 P0：子 Agent 继承项目记忆

**问题**：子 Agent 缺少项目记忆和编码约束。

**方案**：在子 Agent system prompt 构造时注入项目记忆和编码规则。

**实施位置**：[subagent_runtime.py:236-266](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py#L236-L266) 的 `_build_subagent_system_prompt()`。

**改造思路**：
```python
def _build_subagent_system_prompt(subagent_entry, context, task, work_dir):
    parts = []
    # 1. 身份声明（现有）
    parts.append(f"你是被主 Agent 委派的子 Agent：{subagent_entry.name}")
    # 2. 用户配置的 system_prompt（现有）
    parts.append(subagent_entry.system_prompt)
    # 3. 【新增】项目记忆
    from backend.memory.agent_memory import build_agent_memory_system_section
    memory_section = build_agent_memory_system_section(work_dir)
    if memory_section:
        parts.append(memory_section)
    # 4. 【新增】编码行为约束（精简版）
    parts.append(CODING_BEHAVIOR_RULES_ESSENTIAL)
    # 5. 任务通信规则（现有）
    parts.append("你必须用 report_to_main 工具提交结果...")
    # 6. Skills 上下文（现有）
    # 7. context（现有）
    # 8. task（现有）
    return "\n\n".join(parts)
```

**注意事项**：
- 项目记忆可能较大，需评估 token 占用
- 可考虑注入精简版编码规则（只保留核心约束）

### 5.3 优先级 P1：引入异步子 Agent + 统一任务通知队列

**问题**：当前只有同步阻塞模式，无法实现"派发后继续其他工作"。

**方案**：参考 Claude Code 的异步子 Agent 机制。

**改造思路**：
1. `delegate_to_subagent` 增加 `run_in_background` 参数
2. 异步派发时立即返回 `async_launched` + `task_id`
3. 子 Agent 完成后，通过 `<task-notification>` 消息回注主 Agent
4. 主 Agent 在空闲时消费任务通知队列

**实施位置**：
- [agent_mode.py](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py)：增加异步分支
- [subagent_runtime.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py)：增加后台任务注册
- 新增 `task_notification_queue` 模块

### 5.4 优先级 P1：引入 SendMessage 继续通信

**问题**：子 Agent 一次性返回，无法继续交互。

**方案**：参考 Claude Code 的 `SendMessage` / `TaskStop` 机制。

**改造思路**：
1. 新增 `send_message_to_subagent` 工具，参数为 `task_id` + `message`
2. 子 Agent 保持运行状态（或可恢复状态），接收新消息后继续执行
3. 新增 `stop_subagent` 工具，参数为 `task_id`

**实施位置**：
- [capability_registry.py](file:///d:/agent/MIMOClaw/backend/utils/capability_registry.py)：新增工具定义
- [subagent_runtime.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py)：增加消息队列和恢复逻辑

### 5.5 优先级 P2：引入 Fork 机制（上下文继承）

**问题**：子 Agent 从零开始，无法利用已有对话上下文。

**方案**：参考 Claude Code 的 Fork Subagent，实现上下文继承。

**改造思路**：
1. `delegate_to_subagent` 增加 `inherit_context` 参数
2. 当 `inherit_context=true` 时，将主 Agent 的当前消息历史（或精简版）作为子 Agent 的初始 messages
3. 子 Agent 的 system prompt 使用主 Agent 的 system prompt（或精简版）
4. 共享相同的工具集定义，最大化 Prompt Cache 命中

**注意事项**：
- 需要递归防护（fork 子 Agent 不能再 fork）
- 需要考虑上下文窗口大小限制
- 可能需要实现上下文压缩/精简逻辑

### 5.6 优先级 P0：引入 Worktree 文件级隔离

**问题**：当实现真正的并行委派（5.1）后，多个子 Agent 同时操作同一工作目录会导致写入冲突、状态干扰、文件不可区分三类问题。

**方案**：参考 Claude Code 的 Git Worktree 隔离机制，为每个并行子 Agent 创建独立工作目录。

**改造思路**：
1. `delegate_to_subagent` 增加 `isolation: "worktree"` 参数
2. 在 `run_subagent()` 启动前调用 `git worktree add -b worktree/<task-id> <path> <base>`
3. 子 Agent 的所有文件操作（read/write/edit）在该 worktree 目录内执行
4. 子 Agent 完成后：
   - **有变更** → 保留 worktree，返回 worktreePath 供主 Agent 后续合并
   - **无变更** → 自动删除 worktree 和分支
5. Worktree 统一存放在 `.Aries/worktrees/<task-id>/`

**关键设计要点**：
- **fail-closed 退出**：删除 worktree 前必须统计未提交文件和新提交，有变更则拒绝删除（除非显式 `discard_changes=true`）
- **快速恢复**：如果目标 worktree 已存在，直接读取 `.git` 指针文件获取 HEAD SHA，跳过 `fetch` + `worktree add`
- **路径安全**：子 Agent 的 cwd 设置为 worktree 路径，所有工具执行在该路径下
- **Sparse Checkout**：对于大型仓库，支持只检出特定目录以加速创建

**实施位置**：
- 新增 `backend/utils/worktree_manager.py`：worktree 创建/删除/统计变更
- [subagent_runtime.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py)：启动前创建 worktree，完成后清理

### 5.7 优先级 P2：模型分层选择

**问题**：子 Agent 配置固定 model，无法按任务复杂度动态选择。

**方案**：参考 Claude Code 的 haiku/sonnet/opus 分层。

**改造思路**：
1. 子 Agent 配置增加 `model_tier` 字段（`fast` / `balanced` / `powerful`）
2. `delegate_to_subagent` 增加可选 `model` 参数，允许主 Agent 按任务复杂度选择
3. 能力注册表中标注每个子 Agent 的推荐模型层级

### 5.8 优先级 P1：引入共享工作空间（Scratchpad + Mailbox）

**问题**：子 Agent 与主 Agent 之间唯一通道是 task（入）和 report_to_main.message（出，限 500 字），无法共享中间产物。

**方案**：参考 Claude Code 的 Scratchpad 和 Swarm Mailbox 机制。

**改造思路**：
1. **Scratchpad 共享目录**：为每次委派创建临时共享目录 `~/.Aries/scratchpad/<task-id>/`
   - 主 Agent 可在 task 中指定 `scratchpad_path`
   - 子 Agent 可将中间结果、文件列表、分析报告写入该目录
   - 多个并行子 Agent 可共享同一 scratchpad（通过主 Agent 指定）
2. **Mailbox 通信**：为每个子 Agent 建立独立 inbox 文件
   - 主 Agent 可通过 `send_message_to_subagent` 向子 Agent 发送后续指令
   - 子 Agent 可通过 `send_message_to_main` 主动请求澄清（而非一次性 report）
3. **report_to_main 改造**：区分 `summary`（≤500 字摘要）和 `detail`（写入文件的详细结果）
   - 主 Agent 收到 summary 后，可选择读取 detail 文件获取完整信息

**实施位置**：
- 新增 `backend/utils/shared_workspace.py`
- [subagent_runtime.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py)：增加 scratchpad 路径注入和 mailbox 轮询

### 5.9 优先级 P3：引入团队共享记忆

**问题**：项目知识（agent.md / rules.md）只存在于本地，团队成员无法共享。

**方案**：参考 Claude Code 的 TeamMem 机制。

**改造思路**：
1. 在 `~/.Aries/memory/team/` 目录存放团队共享记忆文件
2. 主 Agent 和子 Agent 的 system prompt 都注入 team memory 内容
3. 支持增量同步（基于内容哈希），避免重复传输
4. 上传前密钥扫描，防止泄露

**注意事项**：此功能依赖远程存储后端，可作为后期增强项。

### 5.10 优先级 P3：结构化任务分解与结果聚合

**问题**：完全依赖 LLM 判断，无结构化分解和聚合。

**方案**：参考 Claude Code 的命令编排器模式。

**改造思路**：
1. 引入"工作流模板"概念（类似 Claude Code 的 command .md 文件）
2. 模板定义任务分解步骤、每步使用的子 Agent、结果聚合格式
3. 主 Agent 根据模板执行结构化编排

**示例工作流模板**（feature-dev 风格）：
```yaml
name: feature-development
phases:
  - name: exploration
    parallel: true
    agents: [code-explorer]
    count: 2-3
  - name: architecture
    parallel: true
    agents: [code-architect]
    count: 2-3
  - name: review
    parallel: true
    agents: [code-reviewer]
    count: 3
    aggregation:
      format: "## Critical Issues\n## Important Issues\n## Suggestions"
```

### 5.11 优先级 P3：置信度过滤与质量保障

**问题**：无置信度机制，可能产生误报。

**方案**：参考 Claude Code 的置信度过滤。

**改造思路**：
1. `report_to_main` 增加 `confidence` 字段（0-100）
2. 主 Agent 只整合 `confidence >= 80` 的发现
3. 低于阈值的结果标记为"低置信度"，供参考但不作为主要依据

### 5.12 实施路线图

```
阶段 1（P0 - 基础修复）
├── 实现真正的并行委派（asyncio.gather）
├── 子 Agent 继承项目记忆与编码约束
└── 引入 Worktree 文件级隔离（并行安全的必要前提）

阶段 2（P1 - 机制增强）
├── 异步子 Agent + 统一任务通知队列
├── SendMessage 继续通信
└── 共享工作空间（Scratchpad + Mailbox）

阶段 3（P2 - 高级特性）
├── Fork 机制（上下文继承）
└── 模型分层选择

阶段 4（P3 - 结构化编排与团队协作）
├── 工作流模板（任务分解与结果聚合）
├── 置信度过滤
└── 团队共享记忆（TeamMem）
```

---

## 六、附录

### 6.1 Claude Code 官方文档关键文件索引

| 文档 | URL | 核心内容 |
|------|-----|---------|
| Coordinator Mode | https://ccb.agent-aura.top/docs/features/coordinator-mode | 编排者模式：受限工具集、worker 派发、并行优先 |
| Fork Subagent | https://ccb.agent-aura.top/docs/features/fork-subagent | 上下文继承、Prompt Cache 优化、递归防护 |
| Sub-Agents | https://ccb.agent-aura.top/docs/agent/sub-agents | 四类执行路径、权限模型、同步/异步、生命周期 |
| Worktree 隔离 | https://ccb.agent-aura.top/docs/agent/worktree-isolation | Git Worktree 文件级隔离、创建/销毁生命周期、快速恢复、fail-closed |
| 协调者与蜂群模式 | https://ccb.agent-aura.top/docs/agent/coordinator-and-swarm | Coordinator vs Swarm 两种拓扑、五层系统分层、Mailbox 协议、AgentTool 分流 |
| TeamMem | https://ccb.agent-aura.top/docs/features/teammem | 团队共享记忆、GitHub 仓库双向同步、增量上传、密钥扫描 |
| Daemon | https://ccb.agent-aura.top/docs/features/daemon | 后台守护进程、supervisor+worker 多进程、指数退避重启 |

### 6.2 MIMOClaw 后端关键函数索引

| 函数/类 | 文件 | 行号 | 作用 |
|---------|------|------|------|
| `SubagentEntry` | [subagent_manager.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_manager.py) | 32 | 子 Agent 配置数据类 |
| `discover_subagents()` | [subagent_manager.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_manager.py) | 198 | 扫描配置目录加载全部子 Agent |
| `build_subagent_router_section()` | [subagent_manager.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_manager.py) | 297 | 构造主 Agent 路由表 |
| `run_subagent()` | [subagent_runtime.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py) | 325 | 子 Agent 执行入口 |
| `_build_subagent_system_prompt()` | [subagent_runtime.py](file:///d:/agent/MIMOClaw/backend/utils/subagent_runtime.py) | 236 | 构造子 Agent system prompt |
| `stream_agent_mode()` | [agent_mode.py](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py) | 339 | 主 Agent 流式执行主函数 |
| `build_agent_system_prompt_parts()` | [agent_mode.py](file:///d:/agent/MIMOClaw/backend/api/modes/agent_mode.py) | 190 | 主 Agent system prompt 构建 |

### 6.3 Claude Code 源码关键 Agent 索引

| Agent | 文件 | 模型 | 工具集 | 用途 |
|-------|------|------|--------|------|
| code-explorer | [code-explorer.md](file:///d:/agent/MIMOClaw/claude-code-main/plugins/feature-dev/agents/code-explorer.md) | sonnet | 只读 | 代码探索分析 |
| code-architect | [code-architect.md](file:///d:/agent/MIMOClaw/claude-code-main/plugins/feature-dev/agents/code-architect.md) | sonnet | 只读 | 架构方案设计 |
| code-reviewer | [code-reviewer.md](file:///d:/agent/MIMOClaw/claude-code-main/plugins/feature-dev/agents/code-reviewer.md) | sonnet | 只读 | 代码审查 |
| code-reviewer (pr) | [code-reviewer.md](file:///d:/agent/MIMOClaw/claude-code-main/plugins/pr-review-toolkit/agents/code-reviewer.md) | opus | 全部 | PR 审查 |
| code-simplifier | [code-simplifier.md](file:///d:/agent/MIMOClaw/claude-code-main/plugins/pr-review-toolkit/agents/code-simplifier.md) | opus | 全部 | 代码简化 |
| agent-creator | [agent-creator.md](file:///d:/agent/MIMOClaw/claude-code-main/plugins/plugin-dev/agents/agent-creator.md) | sonnet | Write/Read | Agent 生成 |

### 6.4 可复用的设计模式总结

从 Claude Code 官方实现中提取的 15 个可复用模式：

1. **Frontmatter 驱动的 Agent 定义**：通过 YAML frontmatter 声明 Agent 的名称、描述、模型、工具和颜色
2. **Example 驱动的触发机制**：在 description 中嵌入 `<example>` 块定义触发条件
3. **命令作为编排器**：命令文件通过自然语言指令指导 Claude 启动和协调多个 Agent
4. **并行多 Agent 审查**：启动多个相同类型的 Agent 但赋予不同焦点，然后聚合结果
5. **多阶段验证流水线**：haiku 预处理 → sonnet 分析 → opus 验证
6. **置信度过滤**：每个问题附带 0-100 的置信度评分，只报告 >= 80 的问题
7. **文件列表桥接**：子 Agent 返回关键文件列表，父 Agent 读取这些文件来桥接隔离的上下文
8. **最小权限工具限制**：通过 `tools` 字段将 Agent 限制为完成任务所需的最小工具集
9. **状态文件协调**：通过 `.claude/plugin-name.local.md` 文件管理 Agent 状态和依赖关系
10. **Fork 上下文继承**：通过继承父级上下文和共享请求前缀，最大化 Prompt Cache 命中率
11. **Git Worktree 文件级隔离**：为每个并行子 Agent 创建独立工作目录和分支，fail-closed 退出保护
12. **双拓扑选择**：星型 Coordinator（拆解派发综合）vs 团队型 Swarm（长期队友 + mailbox + task list）
13. **Mailbox 协议通信**：按 name 寻址的 inbox 文件，支持 P2P/broadcast/structured protocol，有大小上限和压缩策略
14. **团队共享记忆同步**：基于内容哈希的增量同步 + ETag 乐观锁 + 密钥扫描 + 分批上传
15. **后台守护进程**：supervisor + worker 多进程架构，指数退避重启 + 快速失败检测 + 优雅关闭

---

## 总结

MIMOClaw 后端已实现一套**配置驱动、LLM 编排、同步阻塞、上下文隔离**的单层多 Agent 系统。核心亮点包括：强制激活机制（子 Agent 可用 disabled 的 skill/mcp）、三道防线超时、独立 JSONL 日志、全局取消注册表、能力统一检索。

对照 Claude Code 官方实现（涵盖 Coordinator Mode、Fork Subagent、Sub-Agents、Worktree 隔离、Coordinator 与 Swarm、TeamMem、Daemon 七大机制），最显著的差距是：

1. **并行委派名不副实**（P0）：提示词承诺并发但实现为串行，应使用 `asyncio.gather` 实现真正的并行
2. **子 Agent 上下文缺失**（P0）：子 Agent 不获得项目记忆和编码约束，可能导致行为与项目约定不一致
3. **无文件级隔离**（P0）：并行子 Agent 共享工作目录，实现并行后必然产生写入冲突，需引入 Worktree 隔离
4. **无共享工作空间**（P1）：子 Agent 与主 Agent 间唯一通道是 task/report_to_main，无法共享中间产物，需引入 Scratchpad + Mailbox
5. **无 Fork 机制**（P2）：子 Agent 每次从零开始，无法利用已有上下文，既浪费 token 又降低响应质量

建议按 P0 → P1 → P2 → P3 的优先级逐步实施优化。**特别注意**：Worktree 隔离应与并行委派同步实施——并行委派是"让多个子 Agent 同时跑"，而 Worktree 隔离是"让它们同时跑而不互相破坏"，两者是并行的必要前提和补充。
