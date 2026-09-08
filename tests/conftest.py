"""Общая подготовка для тестов: приложение поднимается на отдельной базе,
чтобы проверки не трогали рабочие данные."""
import os
import tempfile

# Путь к базе задаётся до импорта приложения — модуль app.db читает его при загрузке.
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="finance-test-"), "test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine, seed_articles  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
def client():
    """Чистая база на каждый тест."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_articles(session)
    with TestClient(app) as test_client:
        yield test_client
