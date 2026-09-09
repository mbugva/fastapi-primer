"""
contains routes for the "/users" endpoints.

these routes will not be included in the documentation docs, since they
return formatted output in html & css.

endpoints included here are:
    * CREATE:
    * READ(GET):
        - /users/{user_id}/posts
    * UPDATE:
    * DELETE:
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import func, select

from app.database.config import get_db
from app.config import settings
from app.database import models
from app.main import templates

router = APIRouter(prefix="/users", tags=["users views"], include_in_schema=False)


@router.get("/{user_id}/posts")
async def get_user_posts_by_id(
    request: Request, user_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    "/users/{user_id}/posts"
    returns all posts uploaded by a given user in descending order

    filters these based on the "user_id" passed in as a parameter in the url
    request. if no posts were uploaded by the given user, appropriate
    error message is returned

    NOTE:
    - "selectinload()": allows for eargely loading in the async sqlite session,
      hence the request is able to access "models.Post.author", lest it would
      return and error
    - the first query does not need a "selectinload" method since we are not
      accessing any relationships from the "Users" table. the second query does
      however need it
    - "order_by()": allows ordering by most recent post
    """

    data = await db.execute(select(models.User).where(models.User.id == user_id))
    existing_user = data.scalars().first()

    # fail first, fail loudly, keep success clean
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Looks like the user does not exist. Try again?",
        )

    count_result = await db.execute(
        select(func.count())
        .select_from(models.Post)
        .where(models.Post.user_id == user_id)
    )
    total_posts = count_result.scalar() or 0

    data = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id)
        .order_by(models.Post.date_posted.desc())
        .limit(settings.posts_per_page)
    )
    posts = data.scalars().all()
    has_more = len(posts) < total_posts

    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {
            "posts": posts,
            "user": existing_user,
            "title": f"{existing_user.username.title()}'s Posts",
            "limit": settings.posts_per_page,
            "has_more": has_more,
        },
    )


@router.get("/account")
async def account_page(request: Request):
    """
    less goo
    """
    title: str = "Account"
    return templates.TemplateResponse(request, "account.html", {"title": title})
