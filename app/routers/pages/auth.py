"""
contains routes for the "/auth" endpoints.

these routes will not be included in the documentation docs, since they
return formatted output in html & css.

endpoints included here are:
    * CREATE:
    * READ(GET):
        - /login: login
        - /register: register
    * UPDATE:
    * DELETE:
"""

from fastapi import APIRouter, Request

from app.main import templates

router = APIRouter(prefix="/auth", include_in_schema=False)


@router.get("/register")
async def register(request: Request):
    """
    "/auth/register"
    endpoint that registers new users into the application.

    most of the logic performed is contained inline in the
    "templates/register.html" template, which it renders, formatted in html and
    css. the template calls the "/api/users" endpoint, using javascript, to
    create a new user in the database if all input values are correct. if not
    appropriate errors are returned.

    the user is then redirect to the "/auth/login" route to get their token
    assigned before being logged into the application.
    """
    title: str = "Register"
    return templates.TemplateResponse(request, "register.html", {"title": title})


@router.get("/login")
async def login(request: Request):
    """
    "/auth/login"
    endpoint that logs in existing users into the application.

    most of the logic performed is contained inline in the
    "templates/login.html" template, which it renders, formatted in html and
    css.

    the template calls the "/api/auth/token" endpoint, using javascript,
    which peforms most of the logic, checking if the user exists in the
    database, then assigning them their token and logging them in.
    """
    title: str = "Login"
    return templates.TemplateResponse(request, "login.html", {"title": title})


@router.get("/forgot-password")
async def forgot_password(request: Request):
    """
    "/auth/forgot-password"
    endpoint that render the "forgot_password.html" template, allowing a user
    to input their account email, which, if it exists, will receive a link to
    reset their password.

    the template calls the "api/auth/forgot-password" to verify data passed
    into it
    """
    title: str = "Forgot Password"
    return templates.TemplateResponse(request, "forgot_password.html", {"title": title})


@router.get("/reset-password")
async def reset_password(request: Request):
    """
    "/auth/reset-password"
    endpoint that renders the "reset_password.html" template, which allows a
    user to change their account password.

    NOTE:
    - the "referer-policy" is disable, since when you click alink to another
      website, yourbrowser normally sends data to the new page, informing them
      where you came from. Our reset password URL contains the token as a query
      parameter, and if a user were to click on any other link from here, the
      token will be shared there too, allowing anyone to access the users
      account. this prevents that
    """
    title: str = "Reset password"
    response = templates.TemplateResponse(
        request, "reset_password.html", {"title": title}
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
