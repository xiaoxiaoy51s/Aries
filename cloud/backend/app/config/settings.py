from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aries_cloud"

    # JWT
    JWT_SECRET_KEY: str = "aries-cloud-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 129600  # 90 days

    # SMTP
    SMTP_HOST: str = "smtp.qq.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True

    # App
    APP_NAME: str = "Aries Cloud"
    APP_DEBUG: bool = True
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Verification Code
    CODE_EXPIRE_MINUTES: int = 3
    CODE_LENGTH: int = 6

    # Shell Sandbox
    SHELL_TIMEOUT: int = 30              # 同步命令超时（秒）
    SHELL_MAX_OUTPUT: int = 20000        # 最大输出字符数
    SHELL_MAX_FILE_SIZE: int = 10_000_000  # 工作区单文件上限 10MB
    WORKSPACE_CLEANUP_DAYS: int = 365    # 非 default 工作目录 TTL（天），0=不清理
    SHELL_CLEANUP_HOUR: int = 4          # 每日执行 TTL 清理的小时

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
