"""消息快照工具

新版 agent 模式采用 JSONL 日志（utils.session_logger），本模块只负责
把日志路径写入 chat_messages.message_snapshot_json。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.session_logger import SessionLogger


def create_assistant_snapshot(
    session_id: str,
    logger: "SessionLogger | None" = None,
) -> str:
    """记录一次 assistant 回复的快照标识。

    新版：返回 logger 持有的 JSONL 文件路径，由调用方在创建消息记录时
    一并写入 message_snapshot_json。旧版（无 logger）则返回空串。
    """
    if logger is None:
        return ""
    return logger.jsonl_path_str()


def set_summary_block(snapshot_id: str, summary_text: str = ""):
    """旧版接口，保留为空实现。"""
    pass


def finalize_snapshot(snapshot_id: str, all_events: list | None = None):
    """旧版接口，保留为空实现。"""
    pass
