from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.session import get_session
from app.models import Role, User
from app.schemas.auth import Token, UserOut, UserRegister
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/register", response_model=UserOut)
async def register(payload: UserRegister, session: AsyncSession = Depends(get_session)):
    # email unique check
    result = await session.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # First ever user becomes admin (handy for demo)
    count = (await session.execute(select(func.count(User.id)))).scalar_one()
    role = Role.admin if count == 0 else Role.user


    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)):
    # OAuth2PasswordRequestForm sends `username` field; we treat it as email
    result = await session.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")


    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return Token(access_token=token)