"""
a special file recognized by pytest. its where you place your fixtures(reusable
pieces of test setup that pytest injects into ous tests) and other shared setups
that you would like available in all your tests.

NOTE:
    - for the database, we will be employing the "transactional rollback pattern"
    for fast test isolation. we will create all our database tables once at
    the start of our test session. then each test runs inside a database
    transaction. after each test completes, we rollback our that transcation,
    undoing everything the test just did instantly. finally at the end of the
    test session, we drop all of our database tables.
    this method beats the common way of creating and droping tables for each
    test, plus you no longer have to worry about a tables Foreign Key
    relationships and what not
"""

import os
import collections.abc
from typing import AsyncGenerator

# NOTE: import os environments before main imports to prevent hitting actual api
# alot of CRUD operations will be performed, hence using dummy database, s3, aws
# credentials prevent hitting actual api
os.environ["DATABASE_URL"] = "mariadb+aiomysql://root:root@localhost:3306/test_blog"
os.environ["S3_BUCKET_NAME"] = "test-bucket"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing"

os.environ["S3_ACCESS_KEY_ID"] = "testing"
os.environ["S3_SECRET_ACCESS_KEY"] = "testing"
os.environ["S3_REGION"] = "us-east-1"

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

import boto3
import pytest
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database.config import Base, get_db
from app.main import app

# allow pytest to run async functions due to async db
pytest_plugins = ["anyio"]


@pytest.fixture(scope="session")
def anyio_backend():
    """
    pytest fixture, that is scopes to run once per the entire session. it
    tells pytest to use asyncio for the async operations
    """
    return "asyncio"


@pytest.fixture(scope="session")
def test_engine():
    """
    create the asynchronous test database engine, using the test database url
    we have defined above. also scoped to a session
    """
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
    )
    return engine


@pytest.fixture(scope="session")
async def setup_database(test_engine):
    """
    create all of our tables and after running all tests in the "yield"
    section, clean them up and dispose of the engine
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def db_session(test_engine, setup_database) -> AsyncGenerator[AsyncSession]:
    """
    implement the transactional rollback discussed in file definition

    NOTE:
    - the fixture is not "session" scope, meaning that it is function scoped,
      whichis the default. it runs for every test function
    """
    conn = await test_engine.connect()
    trans = await conn.begin()

    test_async_session = async_sessionmaker(
        bind=conn,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",  # ensure nothing commites to db
    )

    async with test_async_session() as session:
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()  # undo everything test did
            await conn.close()


@pytest.fixture
def mocked_aws():
    """
    mock hitting actual AWS s3 endpoints with moto, as costs can get real high
    real fast. this follow the default scoping, i.e function scoped, meaning
    each test gets a fresh mock state with an empty bucket
    """
    with mock_aws():
        s3 = boto3.client("s3", region_name=os.environ["S3_REGION"])
        s3.create_bucket(Bucket=os.environ["S3_BUCKET_NAME"])
        yield s3


@pytest.fixture
async def client(db_session: AsyncSession, mocked_aws) -> AsyncGenerator[AsyncSession]:
    """
    swaps in the normal database session for the transactional rolled back one,
    all thanks to FastAPI's dependency_overrides, where One canoveride a
    dependency injection value. this is better than trying to mock a database
    connection on each function as it gets complicated fast; trust me I tried it in
    nodejs+express, this is amazing!!

    """

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # tests will run without startign the server or starting the network
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",  # for url redirects
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


"""
create helpers for authentication since many of the routes require that yoube
authenticated and authorized
"""


async def create_test_user(
    client: AsyncClient,
    username: str = "testuser",
    email: str = "test@example.com",
    password: str = "testpassword123",
) -> dict:
    response = await client.post(
        "/api/users",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )
    # assert that the user was created, else give me the given error
    assert response.status_code == 201, f"Failed to create user: {response.text}"
    return response.json()


async def login_user(
    client: AsyncClient,
    username: str = "testuser",
    password: str = "testpassword123",
) -> str:
    response = await client.post(
        "/api/auth/token",
        data={
            "username": username,
            "password": password,
        },
    )
    assert response.status_code == 200, f"Failed to login: {response.text}"
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
