"""微信链接 - stub"""


def generate_qrcode() -> dict:
    return {"success": False, "error": "not implemented"}


def poll_qrcode_status(key: str) -> dict:
    return {"status": "expired"}
