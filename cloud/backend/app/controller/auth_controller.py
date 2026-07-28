from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.service.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ============ DTO ============

class SendCodeRequest(BaseModel):
    email: EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    code: str
    username: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar: str
    registration_date: datetime
    membership_level: int
    gender: int
    role_type: int
    status: int
    signature: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ============ 接口 ============

@router.post("/send-code")
async def send_code(req: SendCodeRequest):
    await AuthService.send_verification_code(req.email)
    return {"message": "验证码已发送，请查收邮箱"}


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    token, user = await AuthService.register(db, req.email, req.code, req.username, req.password)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    token, user = await AuthService.login(db, req.email, req.password)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)
