"""Сквозные проверки через HTTP: то, что увидит пользователь в браузере."""
import re


def article_id(client, name: str) -> int:
    """Достаёт id статьи из формы на странице проекта."""
    page = client.get("/articles").text
    assert name in page
    from app.db import SessionLocal
    from app.models import Article
    from sqlalchemy import select
    with SessionLocal() as session:
        return session.scalar(select(Article).where(Article.name == name)).id


def make_project(client, name="Портал для клиента") -> int:
    response = client.post("/projects", data={"name": name, "description": ""})
    return int(re.search(r"/projects/(\d+)", str(response.url)).group(1))


def test_builtin_articles_are_seeded(client):
    page = client.get("/articles").text
    for name in ["Внешние программисты", "Внутренние программисты",
                 "Расходы на ИИ", "Аренда сервера", "Дивиденды"]:
        assert name in page


def test_project_lifecycle_and_totals(client):
    project_id = make_project(client)

    client.post(f"/projects/{project_id}/entries", data={
        "article_id": article_id(client, "Доход по проекту"),
        "amount": "500 000", "occurred_on": "2026-09-01", "comment": "аванс",
    })
    client.post(f"/projects/{project_id}/entries", data={
        "article_id": article_id(client, "Внешние программисты"),
        "amount": "200000", "occurred_on": "2026-09-02", "comment": "",
    })
    client.post(f"/projects/{project_id}/entries", data={
        "article_id": article_id(client, "Расходы на ИИ"),
        "amount": "50000.50", "occurred_on": "2026-09-03", "comment": "",
    })

    page = client.get(f"/projects/{project_id}").text
    assert "500 000,00" in page          # доходы
    assert "250 000,50" in page          # расходы
    assert "249 999,50" in page          # прибыль
    assert "50,0 %" in page              # рентабельность

    summary = client.get("/").text
    assert "249 999,50" in summary


def test_margin_dash_when_no_income(client):
    project_id = make_project(client, "Только расходы")
    client.post(f"/projects/{project_id}/entries", data={
        "article_id": article_id(client, "Аренда сервера"), "amount": "3000",
    })
    page = client.get(f"/projects/{project_id}").text
    assert "—" in page


def test_bad_amount_is_rejected(client):
    project_id = make_project(client, "Проверка ввода")
    response = client.post(f"/projects/{project_id}/entries", data={
        "article_id": article_id(client, "Дивиденды"), "amount": "не число",
    }, follow_redirects=True)
    assert "Не похоже на сумму" in response.text


def test_custom_article_can_be_added_and_removed(client):
    client.post("/articles", data={"name": "Реклама", "kind": "expense"})
    assert "Реклама" in client.get("/articles").text

    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Article
    with SessionLocal() as session:
        new_id = session.scalar(select(Article).where(Article.name == "Реклама")).id

    client.post(f"/articles/{new_id}/delete")
    assert "Реклама" not in client.get("/articles").text


def test_builtin_article_cannot_be_deleted(client):
    builtin_id = article_id(client, "Дивиденды")
    response = client.post(f"/articles/{builtin_id}/delete", follow_redirects=True)
    assert "Базовую статью удалить нельзя" in response.text
    assert "Дивиденды" in client.get("/articles").text


def test_article_with_entries_is_protected(client):
    client.post("/articles", data={"name": "Подрядчики", "kind": "expense"})
    custom_id = article_id(client, "Подрядчики")
    project_id = make_project(client, "С подрядчиками")
    client.post(f"/projects/{project_id}/entries", data={
        "article_id": custom_id, "amount": "1000",
    })
    response = client.post(f"/articles/{custom_id}/delete", follow_redirects=True)
    assert "есть операции" in response.text


def test_employee_joins_project_and_signs_entry(client):
    client.post("/employees", data={"full_name": "Иванов Иван", "position": "аналитик"})
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Employee
    with SessionLocal() as session:
        employee_id = session.scalar(select(Employee)).id

    project_id = make_project(client, "Командный проект")
    client.post(f"/projects/{project_id}/members", data={"employee_id": employee_id})
    assert "Иванов Иван" in client.get(f"/projects/{project_id}").text

    # выбрали себя в шапке — операция подписывается автором
    client.post("/whoami", data={"employee_id": str(employee_id), "next_url": "/"})
    client.post(f"/projects/{project_id}/entries", data={
        "article_id": article_id(client, "Доход по проекту"), "amount": "10000",
    })
    page = client.get(f"/projects/{project_id}").text
    assert page.count("Иванов Иван") >= 2  # в команде и в авторе операции

    client.post(f"/projects/{project_id}/members/{employee_id}/remove")
    assert "На проекте пока никого нет" in client.get(f"/projects/{project_id}").text


def test_deleting_project_removes_its_entries(client):
    project_id = make_project(client, "Временный")
    client.post(f"/projects/{project_id}/entries", data={
        "article_id": article_id(client, "Доход по проекту"), "amount": "777",
    })
    client.post(f"/projects/{project_id}/delete")
    assert "Временный" not in client.get("/").text

    from app.db import SessionLocal
    from app.models import Entry
    with SessionLocal() as session:
        assert session.query(Entry).count() == 0


def test_bitrix_import_without_portal_reports_clearly(client):
    response = client.post("/employees/import", follow_redirects=True)
    assert "не установлено ни в один портал" in response.text


def test_bitrix_install_saves_portal(client):
    client.post("/b24/install", data={
        "DOMAIN": "example.bitrix24.ru", "AUTH_ID": "token-123",
        "REFRESH_ID": "refresh-123", "member_id": "member-1",
    })
    assert "example.bitrix24.ru" in client.get("/employees").text
