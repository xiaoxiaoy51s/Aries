"""Agent 基础工具 - stub"""
import traceback


def execute(tool: str = "", work_dir: str = "", **kwargs) -> dict:
    """执行基础工具（stub 实现）"""
    try:
        if tool == "cli_executor":
            return {
                "success": False,
                "error": "CLIExecutor not available in stub mode",
                "output": "命令执行器暂不可用",
            }
        return {
            "success": False,
            "error": f"Unknown tool: {tool}",
            "output": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": traceback.format_exc(),
        }
