"""Подключение к базе и наполнение справочника при первом запуске."""
import os
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.finance import EXPENSE, INCOME
from app.models import Article, Base

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "finance.db"))

# Статьи из задания. Их нельзя удалить — только дополнить своими.
BUILTIN_ARTICLES = [
    ("Доход по проекту", INCOME),
    ("Внешние программисты", EXPENSE),
    ("Внутренние программисты", EXPENSE),
    ("Расходы на ИИ", EXPENSE),
    ("Аренда сервера", EXPENSE),
    ("Дивиденды", EXPENSE),
]


def _make_engine(db_path: str = DB_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


def seed_articles(session: Session) -> None:
    """Заводит базовые статьи, если их ещё нет. Повторный вызов безопасен."""
    for name, kind in BUILTIN_ARTICLES:
        exists = session.scalar(select(Article).where(Article.name == name, Article.kind == kind))
        if not exists:
            session.add(Article(name=name, kind=kind, is_builtin=True))
    session.commit()


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_articles(session)


def get_session():
    """Сессия на один запрос — FastAPI закроет её сам."""
    with SessionLocal() as session:
        yield session
