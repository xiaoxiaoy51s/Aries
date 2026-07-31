from app.exception.auth_exception import AuthException


class ModelNotFoundError(AuthException):
    status_code: int = 404
    detail: str = "模型配置不存在"


class DuplicateModelNameError(AuthException):
    detail: str = "存在同一个模型名称，请修改模型名称"
