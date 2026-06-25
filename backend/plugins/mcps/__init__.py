"""内置 MCP 配置目录。

每个子目录代表一个内置 MCP 服务，目录下放一个 JSON 配置文件，例如：
  fetch/
    fetch.json

启动时会被合并到 ~/.Aries/mcp.json（用户已有的配置不会被覆盖）。
"""
