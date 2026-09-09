"""
contains routes for the "/posts" endpoints.

these routes will not be included in the documentation docs, since they
return formatted output in html & css.

endpoints included here are:
    * CREATE:
    * READ(GET):
        - /posts: get_posts
        - /posts/{post_id}: get_post_by_id
    * UPDATE:
    * DELETE:

the C(reate), U(pdate) and D(elete) endpoints for posts not included here work
in tandem with the frontend UI. the displayed pages will call the needed
backend API in "/api/posts" to perform essential operations. this is with the
help of javascript embeded in the pages.
"""

from typing import Annotated

from fastapi import Depends, Request, status, HTTPException, APIRouter, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.main import templates
from app.config import settings
from app.database import models
from app.database.config import get_db
from app.schemas.posts import PaginatedPostResponse

router = APIRouter(prefix="/posts", tags=["post views"], include_in_schema=False)


@router.get("")
async def get_posts(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    "/posts"
    main url that appears upon loading the application. it returns all the posts
    currently present in the database, displayed using html and css in the
    "templates/home.html" template
    initially the first 10posts will be rendered by the API, hence displayed
    fast. since pagination with limit..offset has been implemented, we use
    javascript to fetch more from the API.

    NOTE:
    - "selectinload": in synchronous SQLAlchemy, lazy loading just works. for
      the "Post" object, SQLAlchemy automatically runs a query to load
      "Post.author" when you try to access it, hence templates are able to
      acces "post.author.username" with no issues. for async SQLAlchemy, lazy
      loading is not supported hence the above will result in errors; this is
      fixed by eagerly loading! "selectinload" enables this by telling
      SQLAlchemy to load things immediately alongside the main query.
    - it implements pagination via limit...offset. since we expect the default
      home page to always have some posts, there will be no offset, only limit,
      that will beimplemented by a "Load more" button in the templates.
      limit is defined to be >1 and <100, its default is 10.
    """

    title: str = "Homepage"

    count_result = await db.execute(select(func.count()).select_from(models.Post))
    total_posts = count_result.scalar() or 0

    data = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .order_by(models.Post.date_posted.desc())
        .limit(settings.posts_per_page)
    )
    posts = data.scalars().all()

    # true if skipped + length of posts < total posts. else false since all
    # have been returned
    has_more = len(posts) < total_posts

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "posts": posts,
            "title": title,
            "limit": settings.posts_per_page,
            "has_more": has_more,
        },
        status.HTTP_200_OK,
    )


@router.get("/{post_id}")
async def get_post_by_id(
    post_id: int, request: Request, db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    "/posts/{post_id}"
    it returns a single post formatted using html and css in the
    "templates/home.html" template.

    filtering is done based on the "post_id" value passed in as a parameter,
    and if no such post exists, appropriate error messages are returned.

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

    # fail first, fail visibly
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oh no! It looks like the post does not exist. Try again?",
        )

    title: str = post.title[:50]
    return templates.TemplateResponse(
        request, "post.html", {"post": post, "title": title}, status.HTTP_200_OK
    )
