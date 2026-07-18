---
name: cli-tools
description: "当用户需要理解整个理解项目用途时候，当你疑惑各种CLI(claude,opencode,codex等)使用方法的时候,还有你在运行github仓库的时候,此skill里面记录了这些工具的使用方法"
---

# cli-tools — 项目理解、CLI 工具与 GitHub 仓库管理

## 概述

本 skill 是 Aries 项目的能力聚合入口，涵盖三个核心领域：

1. **项目理解** — 了解 Aries 的整体架构、模块划分、技术栈和运行方式，为 AI 提供项目层面的上下文感知
2. **CLI 工具管理** — 检测系统中已安装的终端 AI 编码代理 CLI 工具（Claude Code、OpenCode、Codex 等），并将子 Agent 任务委派给这些工具执行
3. **GitHub 仓库管理** — 通过 Personal Access Token（PAT）认证，管理远程仓库的代码提交、推送、拉取和分支操作

## 路由规则

根据用户意图，路由到对应的子文档执行具体操作：

| 意图关键词 | 路由目标 | 说明 |
|-----------|---------|------|
| 项目架构、模块、技术栈、目录结构 | `project-features.md` | 项目功能文档（待用户补充） |
| CLI 工具、子 Agent 委派、编码代理 | `cli.md` | 终端 AI 编码代理 CLI 工具调用路由 |
| GitHub、仓库、提交、推送、分支 | `github.md` | GitHub 仓库认证与代码管理 |

## 工作原理

1. **接收用户请求**，解析意图分类
2. **路由到对应子文档**，获取该领域的详细指令
3. **执行具体操作**，必要时结合 Aries 后端的 API 端点
4. **返回结果**，总结执行状态

## 相关后端 API

Aries 后端提供以下相关接口（供 AI 直接调用）：

- **GitHub**: `POST /github/check-token`、`POST /github/set-token`、`POST /git/push`、`POST /git/pull` 等
- **CLI 路由**: 由 `backend/utils/tools_status.py` 中的 `CLI_ROUTING_CONFIGS` 控制
- **文件操作**: `POST /files/revert`、`GET /files/read`、`PUT /files/save` 等
