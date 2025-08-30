from datetime import datetime, timezone

from app.db.session import get_session
from app.deps import require_roles
from app.models import Post, PostStatus, Role, User
from app.schemas.post import PostOut
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/reviews", response_model=list[PostOut])
async def list_pending(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles(Role.admin))
):
    result = await session.execute(
        select(Post)
        .where(Post.status == PostStatus.pending_review)
        .order_by(Post.created_at)
    )
    return result.scalars().all()


@router.post("/reviews/{post_id}/approve", response_model=PostOut)
async def approve(
    post_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles(Role.admin))
):
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    post.status = PostStatus.published
    post.published_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(post)
    return post


@router.post("/reviews/{post_id}/reject", response_model=PostOut)
async def reject(
    post_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles(Role.admin))
):
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    post.status = PostStatus.rejected
    await session.commit()
    await session.refresh(post)
    return post