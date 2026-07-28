class AuthException(Exception):
    """认证基础异常"""
    status_code: int = 400
    detail: str = "认证错误"


class VerificationCodeError(AuthException):
    detail: str = "验证码错误或已过期"


class UserAlreadyExistsError(AuthException):
    detail: str = "该邮箱已注册"


class UsernameTakenError(AuthException):
    detail: str = "用户名已被使用"


class InvalidCredentialsError(AuthException):
    status_code: int = 401
    detail: str = "邮箱或密码错误"


class AccountDisabledError(AuthException):
    status_code: int = 403
    detail: str = "账号已被禁用"


class UserNotFoundError(AuthException):
    status_code: int = 404
    detail: str = "用户不存在"


class InvalidTokenError(AuthException):
    status_code: int = 401
    detail: str = "token无效或已过期"
