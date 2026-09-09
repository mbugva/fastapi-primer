"""
main entrypoint of the application. to run the program:
    $ fastapi dev

once the server has been started, api documentation can be found at:
    - https:127.0.0.1:8000/docs
    - https:127.0.0.1:8000/redoc
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)

from app.database.config import engine
from app.database import models


# create our database by looking at our models and creating them, if they
# do not exist. also, this method is idempotent hence safe to run
# multiple times as it cleans up automatically
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    lifespan is a modern method in FastAPI to handle the startup and
    shutdown of events. they replace deprecated "on_startup"/"on_shutdown"
    that were common in Flask applications.

    previously, the db was created with
    "Base.metadata.create_all(bind=engine)". "create_all()" was synchronous,
    hence unable to be called alongside asynchronous methods.
    lifespans allow for this

    now database schema is handled by alembic and not app startup. its better
    for migrations, which allow rollbacks and such
    """
    yield

    # shutdown
    await engine.dispose()


app = FastAPI(
    title="fastapi-primer",
    description="simple app for recording user posts",
    version="0.0.1",
    lifespan=lifespan,
    license_info={
        "name": "GPLv3",
        "url": "https://www.gnu.org/licenses/gpl-3.0.en.html",
    },
    # enable this once the project goes live, to disable the api docs
    # openapi_url=None,
)

templates: Jinja2Templates = Jinja2Templates(directory="templates")  # html
app.mount("/static", StaticFiles(directory="static"), name="static")  # css

# import & register the routes
from app.routers.pages.home import router as home_router
from app.routers.pages.posts import router as posts_router
from app.routers.pages.users import router as users_router
from app.routers.pages.auth import router as auth_router
from app.routers.api_v1.users import router as users_api_router
from app.routers.api_v1.posts import router as posts_api_router
from app.routers.api_v1.auth import router as auth_api_router

app.include_router(home_router)
app.include_router(users_router)
app.include_router(posts_router)
app.include_router(auth_router)
app.include_router(users_api_router)
app.include_router(posts_api_router)
app.include_router(auth_api_router)

# error handling
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handler(
    request: Request, exception: StarletteHTTPException
):
    """
    handle exception errors asynchronously.
    this catches any StarletteHTTPException's raised via code execution.

    fastapi is built on top of starlette, hence why its execptions are also imported
    alongside those of fastapi, lest some will be missed.
    """
    # if url starts with "/api/..."
    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again?"
    )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )


# Validation Error Handling
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exception: RequestValidationError
):
    """
    handle validation errors asynchronously
    """

    # if url starts with "/api/..." return JSON response
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exception)

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request, please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
