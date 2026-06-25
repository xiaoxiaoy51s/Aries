"""
内置插件目录结构：
  backend/plugins/
    skills/   - 自带技能（带 Python 代码 + SKILL.md）
    tools/    - 纯 JSON 工具定义（轻量工具，执行器在 utils/plugin_executor.py）
    agents/   - 自带子 Agent 配置
    mcps/     - 自带 MCP 服务配置

启动时由 utils/plugin_manager.py 同步到 ~/.Aries/plugins/
"""
