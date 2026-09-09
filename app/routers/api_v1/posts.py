"""
contain routes for the "/api/posts" endpoints. they return data in JSON format

also these endpoints are what is included in the OpenAPI documentation in:
    - https:127.0.0.1:8000/docs
    - https:127.0.0.1:8000/redoc

endpoints included here are:
    * CREATE(POST):
        - /api/posts: create_post
    * READ(GET):
        - /api/posts: get_posts
        - /api/posts/{post_id}: get_post_by_id
    * UPDATE:
        - PUT: /api/post/{post_id}: update_post_full
        - PATCH: /api/post/{post_id}: update_post_partial
    * DELETE:
        - /api/posts/{post_id}: delete_post_by_id
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import models
from app.config import settings
from app.database.config import get_db
from app.schemas.posts import (
    PostCreate,
    PostResponse,
    PostUpdate,
    PaginatedPostResponse,
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/posts", tags=["posts"])


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post: PostCreate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    "/api/posts"
    creates new posts in the application

    NOTE:
    - "current_user" is a dependecy for authorization, it protects this route,
      ensuring only authenticated users can access it, else they get a 401
      Unauthorized error. As such, no need to verify user exists first.
    - "attribute_names" in the db.commit() refreshes the post alongside the
      table from the relationship passed in, thus ensuring that table values
      and their relationship values are up-to-date
    """
    new_post = models.Post(
        title=post.title, content=post.content, user_id=current_user.id
    )
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])

    return new_post


@router.get("", response_model=PaginatedPostResponse)
async def get_posts(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.posts_per_page,
):
    """
    "/api/posts"
    returns all posts in database

    NOTE:
    - "selectinload()": allows for eargely loading in the async sqlite session,
      hence the request is able to access "models.Post.author", lest it would
      return and error
    - "order_by()": arranges them in descending order such that newest posts
      come first.
    - it implements pagination via limit...offset. skip(offset) and its
      defined to be > 0. the default value is 0.
      limit is defined to be >1 and <100, its default is 10.
    """

    count_result = await db.execute(select(func.count()).select_from(models.Post))
    total_posts = count_result.scalar() or 0

    data = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .order_by(models.Post.date_posted.desc())
        .offset(skip)
        .limit(limit)
    )
    posts = data.scalars().all()

    # true if skipped + length of posts < total posts. else false since all
    # have been returned
    has_more = skip + len(posts) < total_posts

    return PaginatedPostResponse(
        posts=[PostResponse.model_validate(post) for post in posts],
        total=total_posts,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.get("/{post_id}")
async def get_post_by_id(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    "/api/posts/{post_id}"
    returns a specific post by filtering based on the "post_id" passed in.

    NOTE:
    - "selectinload()": allows for eargely loading in the async sqlite session,
      hence the request is able to access "models.Post.author", lest it would
      return and error
    """
    data = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = data.scalars().first()

    # fail first, fail visibly, keep success clean
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oops! Looks like the post does not exist. Try again?",
        )

    return post


@router.put("/{post_id}", response_model=PostResponse)
async def update_post_full(
    post_id: int,
    updated_post: PostCreate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    "/api/posts/{post_id}"
    updates an entire post using the "put" protocol. as such all fields are
    required.

    NOTE:
    - "current_user" is a dependecy for authorization, it protects this route,
      ensuring only authenticated users can access it, else they get a 401
      Unauthorized error. As such, no need to verify user exists first.
    - "selectinload()": allows for eargely loading in the async sqlite session,
      hence the request is able to access "models.Post.author", lest it would
      return and error
    - "attribute_names" in the db.commit() refreshes the post alongside the
      table from the relationship passed in, thus ensuring that table values
      and their relationship values are up-to-date
    """

    data = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = data.scalars().first()

    # ensure post exists
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oops! Looks like the post does not exist. Try again?",
        )

    # user_id's lazima zimatch pia
    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Oops! Looks like you are not authorized to update this post.",
        )

    post.title = updated_post.title
    post.content = updated_post.content

    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post_partial(
    post_id: int,
    updated_post: PostUpdate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    "/api/posts/{post_id}"
    updates a post partially using the "patch" protocol. all fields are
    optional for this update

    NOTE:
    - "current_user" is a dependecy for authorization, it protects this route,
      ensuring only authenticated users can access it, else they get a 401
      Unauthorized error. As such, no need to verify user exists first.
    - "selectinload()": allows for eargely loading in the async sqlite session,
      hence the request is able to access "models.Post.author", lest it would
      return and error
    - "attribute_names" in the db.commit() refreshes the post alongside the
      table from the relationship passed in, thus ensuring that table values
      and their relationship values are up-to-date
    """

    data = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = data.scalars().first()

    # ensure post exists
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oops! Looks like the post does not exist. Try again?",
        )

    # cheki kama user_id's zinamatch
    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Oops! Looks like you are not authorized to update this post.",
        )

    # overwrites only the data fields passed in by the user, and not update all
    # of them, as those maybe become what is set as default ->'None'
    # .model_dump returns a dictionary
    updated_data = updated_post.model_dump(exclude_unset=True)

    for field, value in updated_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post_by_id(
    post_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    "/api/posts/{post_id}"
    deletes a post in the application based on the "post_id" passed in.

    does not return any data, but if successful, the response status code is
    204, which means the intended action has been successfully perfomred, which
    in this case means that the post has been deleted.

    NOTE:
    - "current_user" is a dependecy for authorization, it protects this route,
      ensuring only authenticated users can access it, else they get a 401
      Unauthorized error. As such, no need to verify user exists first.
    """
    data = await db.execute(select(models.Post).where(models.Post.id == post_id))
    existing_post = data.scalars().first()

    if not existing_post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oops! Post not found. Try again?",
        )

    # cheki kama user_id's zinamatch
    if existing_post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Oops! Looks like you are not authorized to delete this post.",
        )

    await db.delete(existing_post)
    await db.commit()
