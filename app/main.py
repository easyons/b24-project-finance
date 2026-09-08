"""Учёт доходов и расходов по проектам.

Работает двумя способами:
  1. Самостоятельно — открыть http://localhost:8000 после docker compose up.
  2. Вкладкой внутри Битрикс24 — портал стучится в /b24/install и /b24/app.
"""
import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import bitrix
from app.db import get_session, init_db
from app.finance import EXPENSE, INCOME, by_article, summarize
from app.models import Article, Employee, Entry, Project
from app.money import AmountError, format_amount, format_percent, parse_amount

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@asynccontextmanager
async def lifespan(_: FastAPI):
    """База и справочник статей готовятся при старте приложения."""
    init_db()
    yield


app = FastAPI(title="Учёт доходов и расходов по проектам", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
templates.env.filters["money"] = format_amount
templates.env.filters["percent"] = format_percent


def back(url: str, msg: str = "", error: str = "") -> RedirectResponse:
    """Возврат на страницу с короткой подписью о результате."""
    params = []
    if msg:
        params.append(f"msg={msg}")
    if error:
        params.append(f"error={error}")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return RedirectResponse(url, status_code=303)


def current_employee(request: Request, session: Session) -> Employee | None:
    """Кто сейчас работает в приложении — выбирается в шапке, хранится в cookie."""
    raw = request.cookies.get("employee_id")
    if not raw or not raw.isdigit():
        return None
    return session.get(Employee, int(raw))


def page_context(request: Request, session: Session) -> dict:
    return {
        "request": request,
        "employees": session.scalars(select(Employee).order_by(Employee.full_name)).all(),
        "me": current_employee(request, session),
        "msg": request.query_params.get("msg", ""),
        "error": request.query_params.get("error", ""),
    }


# ---------------------------------------------------------------- сводка

@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    projects = session.scalars(
        select(Project)
        .options(selectinload(Project.entries).selectinload(Entry.article),
                 selectinload(Project.members))
        .order_by(Project.name)
    ).all()

    rows = []
    total_income = total_expense = 0
    for project in projects:
        summary = summarize(project.entries)
        total_income += summary.income
        total_expense += summary.expense
        rows.append({"project": project, "summary": summary})

    context = page_context(request, session)
    context.update({
        "rows": rows,
        "total": summarize([]) if not rows else None,
        "total_income": total_income,
        "total_expense": total_expense,
        "total_profit": total_income - total_expense,
    })
    return templates.TemplateResponse(request, "index.html", context)


@app.post("/projects")
def create_project(name: str = Form(...), description: str = Form(""),
                   session: Session = Depends(get_session)):
    name = name.strip()
    if not name:
        return back("/", error="Название проекта не может быть пустым")
    if session.scalar(select(Project).where(Project.name == name)):
        return back("/", error="Проект с таким названием уже есть")
    project = Project(name=name, description=description.strip())
    session.add(project)
    session.commit()
    return back(f"/projects/{project.id}", msg="Проект создан")


@app.post("/projects/{project_id}/delete")
def delete_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if project:
        session.delete(project)
        session.commit()
    return back("/", msg="Проект удалён")


# ---------------------------------------------------------------- карточка проекта

@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_page(project_id: int, request: Request, session: Session = Depends(get_session)):
    project = session.get(
        Project, project_id,
        options=[selectinload(Project.entries).selectinload(Entry.article),
                 selectinload(Project.entries).selectinload(Entry.author),
                 selectinload(Project.members)],
    )
    if project is None:
        return back("/", error="Проект не найден")

    entries = sorted(project.entries, key=lambda e: (e.occurred_on, e.id), reverse=True)
    summary = summarize(project.entries)
    income_articles = session.scalars(
        select(Article).where(Article.kind == INCOME).order_by(Article.name)).all()
    expense_articles = session.scalars(
        select(Article).where(Article.kind == EXPENSE).order_by(Article.name)).all()
    member_ids = {m.id for m in project.members}

    context = page_context(request, session)
    context.update({
        "project": project,
        "entries": entries,
        "summary": summary,
        "income_articles": income_articles,
        "expense_articles": expense_articles,
        "breakdown_income": by_article([e for e in project.entries if e.kind == INCOME]),
        "breakdown_expense": by_article([e for e in project.entries if e.kind == EXPENSE]),
        "free_employees": [e for e in context["employees"] if e.id not in member_ids],
        "today": date.today().isoformat(),
    })
    return templates.TemplateResponse(request, "project.html", context)


@app.post("/projects/{project_id}/entries")
def add_entry(project_id: int, request: Request, article_id: int = Form(...),
              amount: str = Form(...), occurred_on: str = Form(""), comment: str = Form(""),
              session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if project is None:
        return back("/", error="Проект не найден")
    article = session.get(Article, article_id)
    if article is None:
        return back(f"/projects/{project_id}", error="Статья не найдена")
    try:
        cents = parse_amount(amount)
    except AmountError as exc:
        return back(f"/projects/{project_id}", error=str(exc))

    try:
        when = date.fromisoformat(occurred_on) if occurred_on else date.today()
    except ValueError:
        return back(f"/projects/{project_id}", error="Дата указана неверно")

    author = current_employee(request, session)
    session.add(Entry(
        project_id=project.id, article_id=article.id, amount=cents,
        occurred_on=when, comment=comment.strip(),
        author_id=author.id if author else None,
    ))
    session.commit()
    return back(f"/projects/{project_id}", msg="Операция добавлена")


@app.post("/entries/{entry_id}/delete")
def delete_entry(entry_id: int, session: Session = Depends(get_session)):
    entry = session.get(Entry, entry_id)
    if entry is None:
        return back("/", error="Операция не найдена")
    project_id = entry.project_id
    session.delete(entry)
    session.commit()
    return back(f"/projects/{project_id}", msg="Операция удалена")


@app.post("/projects/{project_id}/members")
def add_member(project_id: int, employee_id: int = Form(...),
               session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    employee = session.get(Employee, employee_id)
    if project is None or employee is None:
        return back(f"/projects/{project_id}", error="Сотрудник не найден")
    if employee not in project.members:
        project.members.append(employee)
        session.commit()
    return back(f"/projects/{project_id}", msg="Сотрудник добавлен на проект")


@app.post("/projects/{project_id}/members/{employee_id}/remove")
def remove_member(project_id: int, employee_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    employee = session.get(Employee, employee_id)
    if project and employee and employee in project.members:
        project.members.remove(employee)
        session.commit()
    return back(f"/projects/{project_id}", msg="Сотрудник снят с проекта")


# ---------------------------------------------------------------- справочник статей

@app.get("/articles", response_class=HTMLResponse)
def articles_page(request: Request, session: Session = Depends(get_session)):
    context = page_context(request, session)
    context.update({
        "income_articles": session.scalars(
            select(Article).where(Article.kind == INCOME).order_by(Article.name)).all(),
        "expense_articles": session.scalars(
            select(Article).where(Article.kind == EXPENSE).order_by(Article.name)).all(),
    })
    return templates.TemplateResponse(request, "articles.html", context)


@app.post("/articles")
def create_article(name: str = Form(...), kind: str = Form(...),
                   session: Session = Depends(get_session)):
    name = name.strip()
    if not name:
        return back("/articles", error="Название статьи не может быть пустым")
    if kind not in (INCOME, EXPENSE):
        return back("/articles", error="Непонятный тип статьи")
    if session.scalar(select(Article).where(Article.name == name, Article.kind == kind)):
        return back("/articles", error="Такая статья уже есть")
    session.add(Article(name=name, kind=kind, is_builtin=False))
    session.commit()
    return back("/articles", msg="Статья добавлена")


@app.post("/articles/{article_id}/delete")
def delete_article(article_id: int, session: Session = Depends(get_session)):
    article = session.get(Article, article_id, options=[selectinload(Article.entries)])
    if article is None:
        return back("/articles", error="Статья не найдена")
    if article.is_builtin:
        return back("/articles", error="Базовую статью удалить нельзя")
    if article.entries:
        return back("/articles", error="По статье есть операции, сначала удалите их")
    session.delete(article)
    session.commit()
    return back("/articles", msg="Статья удалена")


# ---------------------------------------------------------------- сотрудники

@app.get("/employees", response_class=HTMLResponse)
def employees_page(request: Request, session: Session = Depends(get_session)):
    context = page_context(request, session)
    context["portal"] = bitrix.active_portal(session)
    return templates.TemplateResponse(request, "employees.html", context)


@app.post("/employees")
def create_employee(full_name: str = Form(...), position: str = Form(""),
                    session: Session = Depends(get_session)):
    full_name = full_name.strip()
    if not full_name:
        return back("/employees", error="Имя не может быть пустым")
    if session.scalar(select(Employee).where(Employee.full_name == full_name)):
        return back("/employees", error="Такой сотрудник уже есть")
    session.add(Employee(full_name=full_name, position=position.strip()))
    session.commit()
    return back("/employees", msg="Сотрудник добавлен")


@app.post("/employees/{employee_id}/delete")
def delete_employee(employee_id: int, session: Session = Depends(get_session)):
    employee = session.get(Employee, employee_id)
    if employee:
        session.delete(employee)
        session.commit()
    return back("/employees", msg="Сотрудник удалён")


@app.post("/employees/import")
def import_from_bitrix(session: Session = Depends(get_session)):
    try:
        added, skipped = bitrix.import_employees(session)
    except bitrix.BitrixError as exc:
        return back("/employees", error=str(exc))
    return back("/employees", msg=f"Из Битрикс24 добавлено: {added}, уже были: {skipped}")


@app.post("/whoami")
def set_current_employee(employee_id: str = Form(""), next_url: str = Form("/")):
    response = RedirectResponse(next_url, status_code=303)
    if employee_id.isdigit():
        response.set_cookie("employee_id", employee_id, max_age=60 * 60 * 24 * 365)
    else:
        response.delete_cookie("employee_id")
    return response


# ---------------------------------------------------------------- Битрикс24

async def _remember_portal(request: Request, session: Session) -> None:
    """Битрикс присылает домен и токены формой — сохраняем их."""
    form = await request.form()
    domain = form.get("DOMAIN") or request.query_params.get("DOMAIN")
    token = form.get("AUTH_ID") or request.query_params.get("AUTH_ID")
    if domain and token:
        bitrix.save_portal(
            session, domain=domain, access_token=token,
            refresh_token=form.get("REFRESH_ID", ""),
            member_id=form.get("member_id", ""),
        )


@app.api_route("/b24/install", methods=["GET", "POST"], response_class=HTMLResponse)
async def b24_install(request: Request, session: Session = Depends(get_session)):
    await _remember_portal(request, session)
    return templates.TemplateResponse(request, "b24_install.html", {})


@app.api_route("/b24/app", methods=["GET", "POST"], response_class=HTMLResponse)
async def b24_app(request: Request, session: Session = Depends(get_session)):
    await _remember_portal(request, session)
    return RedirectResponse("/", status_code=303)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
