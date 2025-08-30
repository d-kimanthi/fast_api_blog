from datetime import datetime, timezone
from typing import Optional

from app.db.session import get_session
from app.deps import get_current_user, require_roles
from app.models import Post, PostStatus, Role, User
from app.schemas.post import PostCreate, PostOut, PostPublic, PostUpdate
from app.utils.slugify import slugify
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter()

@router.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: PostCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles(Role.user, Role.admin)),
):
    """Create a new draft post."""
    # Generate unique slug
    base_slug = slugify(payload.title)
    slug_count = (await session.execute(
        select(func.count(Post.id)).where(Post.slug.like(f"{base_slug}%"))
    )).scalar_one()
    
    slug = base_slug if slug_count == 0 else f"{base_slug}-{slug_count}"
    
    post = Post(
        title=payload.title,
        slug=slug,
        body=payload.body,
        author_id=current_user.id,
        status=PostStatus.draft,
        created_at=datetime.now(timezone.utc)
    )
    
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post

@router.put("/posts/{post_id}", response_model=PostOut)
async def update_post(
    post_id: int,
    payload: PostUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update an existing post (only drafts can be updated)."""
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Authorization check
    if post.author_id != current_user.id and current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Not authorized to edit this post")
    
    # Only allow editing of drafts
    if post.status != PostStatus.draft:
        raise HTTPException(
            status_code=400, 
            detail="Only draft posts can be edited"
        )
    
    # Update fields if provided
    if payload.title is not None:
        post.title = payload.title
        # Regenerate slug if title changed
        base_slug = slugify(payload.title)
        slug_count = (await session.execute(
            select(func.count(Post.id)).where(
                and_(Post.slug.like(f"{base_slug}%"), Post.id != post_id)
            )
        )).scalar_one()
        post.slug = base_slug if slug_count == 0 else f"{base_slug}-{slug_count}"
    
    if payload.body is not None:
        post.body = payload.body
    
    post.updated_at = datetime.now(timezone.utc)
    
    await session.commit()
    await session.refresh(post)
    return post

@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a post (only drafts can be deleted)."""
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Authorization check
    if post.author_id != current_user.id and current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Not authorized to delete this post")
    
    # Only allow deletion of drafts
    if post.status != PostStatus.draft:
        raise HTTPException(
            status_code=400,
            detail="Only draft posts can be deleted"
        )
    
    await session.delete(post)
    await session.commit()

@router.post("/posts/{post_id}/submit", response_model=PostOut)
async def submit_for_review(
    post_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Submit a draft post for review."""
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Authorization check
    if post.author_id != current_user.id and current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Can only submit drafts for review
    if post.status != PostStatus.draft:
        raise HTTPException(
            status_code=400,
            detail="Only draft posts can be submitted for review"
        )
    
    post.status = PostStatus.pending_review
    post.submitted_at = datetime.now(timezone.utc)
    
    await session.commit()
    await session.refresh(post)
    return post

@router.post("/posts/{post_id}/publish", response_model=PostOut)
async def publish_post(
    post_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles(Role.admin)),
):
    """Publish a post (admin only)."""
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Can publish drafts or posts under review
    if post.status not in [PostStatus.draft, PostStatus.pending_review]:
        raise HTTPException(
            status_code=400,
            detail="Post must be in draft or pending review status to be published"
        )
    
    post.status = PostStatus.published
    post.published_at = datetime.now(timezone.utc)
    
    await session.commit()
    await session.refresh(post)
    return post

@router.post("/posts/{post_id}/reject", response_model=PostOut)
async def reject_post(
    post_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles(Role.admin)),
):
    """Reject a post under review (admin only)."""
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.status != PostStatus.pending_review:
        raise HTTPException(
            status_code=400,
            detail="Only posts pending review can be rejected"
        )
    
    post.status = PostStatus.draft
    post.rejected_at = datetime.now(timezone.utc)
    
    await session.commit()
    await session.refresh(post)
    return post

@router.get("/posts/me", response_model=list[PostOut])
async def my_posts(
    status: Optional[PostStatus] = Query(None, description="Filter by post status"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get current user's posts with optional status filtering."""
    query = select(Post).where(Post.author_id == current_user.id)
    
    if status:
        query = query.where(Post.status == status)
    
    query = query.order_by(Post.created_at.desc())
    result = await session.execute(query)
    return result.scalars().all()

@router.get("/posts/pending", response_model=list[PostOut])
async def pending_posts(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles(Role.admin)),
):
    """Get posts pending review (admin only)."""
    result = await session.execute(
        select(Post)
        .where(Post.status == PostStatus.pending_review)
        .order_by(Post.submitted_at.desc())
        .options(selectinload(Post.author))  # Eager load author info
    )
    return result.scalars().all()

@router.get("/articles", response_model=list[PostPublic])
async def public_articles(
    limit: int = Query(10, ge=1, le=100, description="Number of articles to return"),
    offset: int = Query(0, ge=0, description="Number of articles to skip"),
    session: AsyncSession = Depends(get_session)
):
    """Get published articles with pagination."""
    result = await session.execute(
        select(Post)
        .where(Post.status == PostStatus.published)
        .order_by(Post.published_at.desc())
        .limit(limit)
        .offset(offset)
        .options(selectinload(Post.author))  # Include author info
    )
    posts = result.scalars().all()
    return posts

@router.get("/articles/{slug}", response_model=PostPublic)
async def article_detail(
    slug: str, 
    session: AsyncSession = Depends(get_session)
):
    """Get a specific published article by slug."""
    result = await session.execute(
        select(Post)
        .where(and_(Post.slug == slug, Post.status == PostStatus.published))
        .options(selectinload(Post.author))  # Include author info
    )
    post = result.scalar_one_or_none()
    
    if not post:
        raise HTTPException(
            status_code=404, 
            detail="Article not found or not published"
        )
    
    # Optionally increment view count here
    # post.view_count = (post.view_count or 0) + 1
    # await session.commit()
    
    return post

@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(
    post_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get a specific post by ID (for editing/viewing own posts)."""
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Users can only see their own posts unless they're admin
    if post.author_id != current_user.id and current_user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this post")
    
    return post