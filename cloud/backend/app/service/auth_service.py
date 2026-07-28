from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.exception.auth_exception import (
    AccountDisabledError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserAlreadyExistsError,
    UserNotFoundError,
    UsernameTakenError,
    VerificationCodeError,
)
from app.model.user import User
from app.repository.user_repository import UserRepository
from app.service.email_service import generate_code, send_verification_code
from app.utils.code_store import store_code, verify_code
from app.utils.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class AuthService:
    """认证业务逻辑层"""

    @staticmethod
    async def send_verification_code(email: str):
        code = generate_code(settings.CODE_LENGTH)
        await store_code(email, code)
        await send_verification_code(email, code)

    @staticmethod
    async def register(
        db: AsyncSession, email: str, code: str, username: str, password: str
    ) -> tuple[str, User]:
        if not await verify_code(email, code):
            raise VerificationCodeError()
        if await UserRepository.find_by_email(db, email):
            raise UserAlreadyExistsError()
        if await UserRepository.find_by_username(db, username):
            raise UsernameTakenError()

        user = await UserRepository.create(
            db, email=email, username=username, password=hash_password(password)
        )
        token = create_access_token({"sub": str(user.id)})
        return token, user

    @staticmethod
    async def login(db: AsyncSession, email: str, password: str) -> tuple[str, User]:
        user = await UserRepository.find_by_email(db, email)
        if not user or not verify_password(password, user.password):
            raise InvalidCredentialsError()
        if user.status != 1:
            raise AccountDisabledError()

        token = create_access_token({"sub": str(user.id)})
        return token, user

    @staticmethod
    async def get_user_from_token(db: AsyncSession, token: str) -> User:
        try:
            payload = decode_access_token(token)
            user_id = int(payload.get("sub", 0))
        except Exception:
            raise InvalidTokenError()

        user = await UserRepository.find_by_id(db, user_id)
        if not user:
            raise UserNotFoundError()
        return user
