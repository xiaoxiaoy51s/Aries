from app.exception.auth_exception import AuthException


class ModelNotFoundError(AuthException):
    status_code: int = 404
    detail: str = "模型配置不存在"
