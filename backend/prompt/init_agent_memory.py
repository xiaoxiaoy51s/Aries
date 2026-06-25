"""
Init Agent Memory 的 Prompt 模板
让 AI 生成当前项目的 agent.md 记忆文件
"""

INIT_AGENT_MEMORY_PROMPT = """Generate a file named AGENTS.md that serves as a contributor guide for this repository.
Your goal is to produce a clear, concise, and well-structured document with descriptive headings and actionable explanations for each section.
Follow the outline below, but adapt as needed — add sections if relevant, and omit those that do not apply to this project.

Document Requirements

- Title the document "Repository Guidelines".
- Use Markdown headings (#, ##, etc.) for structure.
- Keep the document concise. 200-400 words is optimal.
- Keep explanations short, direct, and specific to this repository.
- Provide examples where helpful (commands, directory paths, naming patterns).
- Maintain a professional, instructional tone.

Recommended Sections

Agent Role

- Define the AI agent's role in this project (e.g., "You are a coding agent focused on backend Python development").
- Specify what the agent should and should not do.
- Include any behavioral rules the agent must follow (e.g., "search before acting", "read files before editing").

Architecture Overview

- Explain the high-level architecture: how modules connect, what the data flow looks like.
- Identify the core entry points and key abstractions.
- Describe the relationship between frontend/backend/database/external services.

Project Structure & Module Organization

- Outline the project structure, including where the source code, tests, and assets are located.
- For each important directory, explain its purpose and any constraints (e.g., "backend/utils/ contains shared utilities, do not add business logic here").

Directory Constraints

- Specify which directories have special rules (e.g., "do not commit .Aries_tmp/", "config.json must not contain real API keys").
- Note any auto-generated directories that should not be manually edited.

Build, Test, and Development Commands

- List key commands for building, testing, and running locally (e.g., npm test, make build).
- Briefly explain what each command does.

Coding Style & Naming Conventions

- Specify indentation rules, language-specific style preferences, and naming patterns.
- Include any formatting or linting tools used.

Tool Usage Priorities

- If this project has custom tools (like search_file, list_files powered by ripgrep), note which tools the agent should prefer over shell equivalents.
- Specify any tool-specific conventions (e.g., "use search_file instead of shell grep for better performance").

Testing Guidelines

- Identify testing frameworks and coverage requirements.
- State test naming conventions and how to run tests.

Commit & Pull Request Guidelines

- Summarize commit message conventions found in the project's Git history.
- Outline pull request requirements (descriptions, linked issues, screenshots, etc.).

(Optional) Add other sections if relevant, such as Security & Configuration Tips, or Agent-Specific Instructions.

Important: do not create AGENTS.md in the repository. After generating the Markdown content, call write_file with memory=true and the complete content so Aries stores it as the current work_dir agent memory."""
