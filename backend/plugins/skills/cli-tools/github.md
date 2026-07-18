---
name: github
description: "GitHub 仓库管理：通过 Personal Access Token（PAT）认证，执行代码提交、推送、拉取、分支管理等 Git 操作。使用 Aries 后端 API 驱动，无需本地 Git 客户端配置。"
---

# GitHub 仓库管理

## 概述

本 skill 通过 Aries 后端的 GitHub 集成模块，管理远程 GitHub 仓库的代码提交与版本控制操作。认证方式为 Personal Access Token（PAT），无需 OAuth 流程或本地 Git 凭证存储。

## 认证方式

Aries 使用 PAT（Personal Access Token）进行 GitHub 认证：

1. **设置 Token**：用户在 Aries 设置页面的 GitHub 配置中输入 PAT
2. **存储位置**：Token 存储在 `~/.Aries/github_config.json`，不写入 Git 凭证存储
3. **自动注入**：执行 Git 操作时，后端自动将 Token 注入到 HTTPS URL 中
4. **SSH 转 HTTPS**：远程仓库 URL 为 SSH 格式时，自动转换为 HTTPS 格式以支持 Token 认证

## 后端 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/github/check-token` | GET | 检查当前 Token 是否有效并返回 GitHub 用户信息 |
| `/github/set-token` | POST | 设置/更新 GitHub Token |
| `/github/auth/start` | GET | 可选 OAuth 流程入口（不推荐，优先使用 PAT） |
| `/git/status` | POST | 查看工作区 Git 状态 |
| `/git/commit` | POST | 提交当前暂存区的变更 |
| `/git/push` | POST | 推送提交到远程仓库（自动注入 Token 认证） |
| `/git/pull` | POST | 从远程仓库拉取最新代码 |
| `/git/log` | POST | 查看提交历史 |
| `/git/diff` | POST | 查看工作区或指定文件的差异 |
| `/git/branch/list` | POST | 列出本地分支 |
| `/git/branch/create` | POST | 创建新分支（可选是否切换过去） |
| `/git/branch/checkout` | POST | 切换到已有分支 |
| `/git/branch/merge` | POST | 合并分支 |
| `/git/branch/rename` | POST | 重命名分支 |
| `/git/branch/delete` | POST | 删除本地分支 |

## 工作流程

### 1. 认证与连接

1. 通过 `/github/check-token` 检查当前连接状态
2. 如果未认证，提示用户设置 PAT（引导到 Aries 设置的 GitHub 页面）
3. Token 需具有 `repo` 权限范围

### 2. 提交代码

1. 通过 `/git/status` 查看工作区变更
2. 暂存变更（AI 工具直接编辑文件后自动处理）
3. 通过 `/git/commit` 提交，包含清晰的中文提交信息
4. 通过 `/git/push` 推送到远程仓库

### 3. 分支管理

1. 通过 `/git/branch/list` 查看所有分支
2. 创建/切换/合并/重命名/删除分支
3. 确保在正确的分支上操作

## 注意事项

- 提交信息使用中文
- Push 操作自动将 SSH URL 转换为 HTTPS URL 以支持 Token 认证
- 如果推送到受保护分支（如 main），可能需要先创建功能分支再提交 PR
- `/files/revert` 可用于回退未提交的文件变更
