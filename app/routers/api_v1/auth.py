"""
contains routes for the "/api/auth" endpoints.

these routes will be included in the OpenAPI documentation in:
    - https:127.0.0.1:8000/docs
    - https:127.0.0.1:8000/redoc

endpoints included here are:
    * CREATE:
    * READ(GET):
        - /api/auth/login: login_for_access_token
        - /api/auth/me: get_current_user
    * UPDATE:
    * DELETE:
"""

from typing import Annotated
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models
from app.database.config import get_db
from app.schemas.users import (
    UserPrivateResponse,
    UserTokenResponse,
    ForgotPasswordRequest,
    ChangePasswordRequest,
    ResetPasswordRequest,
)
from app.utils.auth import get_current_user
from app.utils.passwords import PasswordUtils
from app.utils.tokens import TokenUtils
from app.utils.emails import send_password_reset_email
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/token", response_model=UserTokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    endpoint for assigning tokens to users logging in to the application.

    the "form_data" is parsed by the "OAuth2PasswordRequestForm", which is
    injected as a dependecy. it parses the form for the "username" and
    "password" fields, normally used in OAuth2 validation.

    also through dependecy injection, it creates the database connection, and
    returns those results as the db parameter.

    NOTE:
    - "func.lower()": makes the database value fetched to be in lowercase.
      using this alongside the ".lower()" method for the string being compared
      against allows for case-insensitive searching.
    """
    data = await db.execute(
        select(models.User).where(
            func.lower(models.User.username) == form_data.username.lower()
        )
    )
    existing_user = data.scalars().first()

    # if user does not exists, or paswords dont match fail cleanly
    if not existing_user or not PasswordUtils.verify_password(
        form_data.password, existing_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password. Try again?",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # create token, using "user_id" as sub
    access_token = TokenUtils.create_access_token(data={"sub": str(existing_user.id)})

    return UserTokenResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserPrivateResponse)
async def current_user(
    current_user: Annotated[models.User, Depends(get_current_user)],
):
    """
    endpoint to decode and validate user token. the latter is an essential
    reason as to why we have not implemented this in functionality as an inline
    Js script

    if token is valid, it returns the users data, utilising the
    "UserPrivateResponse" schema.
    """

    return current_user


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    request_data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    endpoint to receive users request to send them an email that allows them to
    reset their passwords. this is accessed from outside the application via
    the "forgot pasword" link in the login pages.

    NOTE:
    - the "202 accepted" status code, means that we have accepted your request
      and are processing it, not confirming that the email exists or not. this
      helps prevent email enumeration attacks via brute force
    - background_tasks: allows for operations to occurr in the background
      without holding app the resources. since sending emails can sometimes be
      a long task, its essential here. however, some tasks may fail hence for
      critical operations such as making payments and such, it would be
      advisable to use task queues like celery or rabbitMq. but for emails,
      they are not critical and users can simply request another
    """
    data = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == request_data.email.lower()
        )
    )
    existing_user = data.scalars().first()

    if existing_user:
        # if user exists, delete any existing reset tokens for that user
        await db.execute(
            sql_delete(models.PasswordResetToken).where(
                models.PasswordResetToken.user_id == existing_user.id
            )
        )

        # then generate the new token
        token = TokenUtils.generate_reset_token()
        token_hash = TokenUtils.hash_reset_token(token)
        expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.reset_expiration_minutes
        )

        # add new token to the database
        reset_token = models.PasswordResetToken(
            user_id=existing_user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(reset_token)
        await db.commit()

        # run the process in the background
        background_tasks.add_task(
            send_password_reset_email,
            to_email=existing_user.email,
            username=existing_user.username,
            token=token,
        )

    # NOTE: stay mysterious :)
    return {
        "message": "If an account exists with this email, you will receive password reset instructions"
    }


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    request_data: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    endpoint gets called when user clicks the reset password link that gets
    delivered to their email after they requested it from the "forgot_password"
    endpoint above. here is where the user(who is not logegd in) actually sets
    their new password.

    NOTE:
    - here we sue the 200 status code. this give the user direct feedback
      telling them where or not the email reset worked.
    """
    # hash submitted token to compare it to what is in our database
    token_hash = TokenUtils.hash_reset_token(request_data.token)

    # lookup token by its hash. if it doesnt exist, return an error
    data = await db.execute(
        select(models.PasswordResetToken).where(
            models.PasswordResetToken.token_hash == token_hash
        )
    )
    reset_token = data.scalars().first()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    # if token exists, actually check if its expired
    if reset_token.expires_at < datetime.now(UTC):
        await db.delete(reset_token)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    data = await db.execute(
        select(models.User).where(models.User.id == reset_token.user_id)
    )
    existing_user = data.scalars().first()

    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    # update user password & delete all existing password reset tokens
    existing_user.password_hash = PasswordUtils.hash_password(request_data.new_password)
    await db.execute(
        sql_delete(models.PasswordResetToken).where(
            models.PasswordResetToken.user_id == existing_user.id
        )
    )
    await db.commit()

    return {
        "message": "Password reset successfully. You can now login with your new password"
    }


@router.patch("/me/password", status_code=status.HTTP_200_OK)
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    endpoint used by logged in users who want to change their password. we use
    the "/me/password" as compared to "/{user_id}" since this removes
    possibilities of any separate authorization checks. the user will already
    be authenticated & authorized in "/me" hence its easier.

    NOTE:
    - using "current_user" means user must be logged in
    - here we sue the 200 status code. this give the user direct feedback
      telling them where or not the email reset worked.
    """

    if not PasswordUtils.verify_password(
        password_data.current_password, current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Oops! Looks like the current passowrd is incorrect. Try again?",
        )

    current_user.password_hash = PasswordUtils.hash_password(password_data.new_password)

    # update user password & delete all existing password reset tokens
    await db.execute(
        sql_delete(models.PasswordResetToken).where(
            models.PasswordResetToken.user_id == current_user.id
        )
    )
    await db.commit()

    return {
        "message": "Password successfully reset",
    }
