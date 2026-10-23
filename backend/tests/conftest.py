import os, sys, tempfile, pathlib
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SUPERVISOR_ENABLED"] = "0"
os.environ["USE_QWEN"] = "off"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fresh(client):
    client.post("/api/reset")
    yield


@pytest.fixture()
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    yield s
    s.close()
