from datetime import datetime, timezone

from app.db.session import get_session
from app.deps import get_current_user, require_roles
from app.models import Post, PostStatus, Role, User
from app.schemas.post import PostCreate, PostOut, PostPublic
from app.utils.slugify import slugify
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/posts", response_model=PostOut)
async def create_post(
    payload: PostCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles(Role.user, Role.admin)),
):
    base = slugify(payload.title)
    count_like = (await session.execute(
        select(func.count(Post.id)).where(Post.slug.like(f"{base}%"))
    )).scalar_one()
    slug = base if count_like == 0 else f"{base}-{count_like + 1}"
    
    post = Post(
        title=payload.title,
        slug=slug,
        body=payload.body,
        author_id=current_user.id
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


@router.post("/posts/{post_id}/submit", response_model=PostOut)
async def submit_for_review(
    post_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.author_id != current_user.id and current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Not allowed")
    
    post.status = PostStatus.pending_review
    await session.commit()
    await session.refresh(post)
    return post


@router.get("/posts/me", response_model=list[PostOut])
async def my_posts(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(Post)
        .where(Post.author_id == current_user.id)
        .order_by(Post.created_at.desc())
    )
    return result.scalars().all()


@router.get("/articles", response_model=list[PostPublic])
async def public_articles(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Post)
        .where(Post.status == PostStatus.published)
        .order_by(Post.published_at.desc())
    )
    posts = result.scalars().all()
    return posts


@router.get("/articles/{slug}", response_model=PostPublic)
async def article_detail(slug: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Post).where(Post.slug == slug, Post.status == PostStatus.published)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(
            status_code=404, 
            detail="Article not found or not published"
        )
    return post