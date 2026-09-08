"""Схема базы: проекты, статьи, операции, сотрудники."""
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Сотрудники на проекте: один человек может вести несколько проектов,
# в проекте может быть несколько человек.
project_members = Table(
    "project_members",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("employee_id", ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True),
)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    entries: Mapped[list["Entry"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    members: Mapped[list["Employee"]] = relationship(
        secondary=project_members, back_populates="projects"
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), unique=True)
    position: Mapped[str] = mapped_column(String(200), default="")
    # id пользователя в Битрикс24, если сотрудник приехал оттуда
    b24_user_id: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)

    projects: Mapped[list[Project]] = relationship(
        secondary=project_members, back_populates="members"
    )


class Article(Base):
    """Статья дохода или расхода. Базовые статьи заводятся при первом запуске,
    свои добавляются через интерфейс."""

    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("name", "kind", name="uq_article_name_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))  # income | expense
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)

    entries: Mapped[list["Entry"]] = relationship(back_populates="article")


class Entry(Base):
    """Одна операция: доход или расход по проекту."""

    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[int] = mapped_column(Integer)  # копейки, всегда больше нуля
    occurred_on: Mapped[date] = mapped_column(Date, default=date.today)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    project: Mapped[Project] = relationship(back_populates="entries")
    article: Mapped[Article] = relationship(back_populates="entries")
    author: Mapped[Employee | None] = relationship()

    @property
    def kind(self) -> str:
        return self.article.kind

    @property
    def article_name(self) -> str:
        return self.article.name


class Portal(Base):
    """Портал Битрикс24, в который установлено приложение.

    Токены живут здесь, чтобы после перезапуска контейнера связь не терялась.
    """

    __tablename__ = "portals"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(200), unique=True)
    access_token: Mapped[str] = mapped_column(String(200))
    refresh_token: Mapped[str] = mapped_column(String(200), default="")
    member_id: Mapped[str] = mapped_column(String(200), default="")
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
