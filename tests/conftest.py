import os

import pytest

os.environ.setdefault("STUDIO_ALLOWED_HOSTS", "localhost,127.0.0.1,renderer,testserver")


@pytest.fixture(autouse=True)
def studio_test_credentials():
    with pytest.MonkeyPatch.context() as env:
        env.setenv("STUDIO_BROWSER_USER", "test-user")
        env.setenv("STUDIO_BROWSER_PASSWORD", "test-browser-password")
        env.setenv("STUDIO_WORKER_TOKEN", "test-worker-token")
        yield


@pytest.fixture()
def dsn():
    value = os.environ.get("STUDIO_TEST_DSN")
    if not value:
        pytest.skip("STUDIO_TEST_DSN não definido (Postgres de teste ausente)")
    return value


@pytest.fixture()
def conn(dsn):
    import psycopg
    connection = psycopg.connect(dsn)
    connection.execute("DROP SCHEMA IF EXISTS studio CASCADE")
    connection.commit()
    yield connection
    connection.close()
