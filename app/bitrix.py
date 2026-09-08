"""Связь с Битрикс24.

Приложение ставится в портал как локальное приложение типа «вкладка».
Битрикс при установке и при каждом открытии присылает POST с доменом портала
и токеном доступа — мы их сохраняем и ходим в REST от имени портала.

Обновление токена по refresh здесь намеренно не делается: Битрикс присылает
свежий токен при каждом открытии вкладки, а фоновых задач у приложения нет.
Если токен всё же протух, достаточно открыть приложение в портале заново.
"""
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Employee, Portal

TIMEOUT = 10.0


class BitrixError(RuntimeError):
    """Портал ответил ошибкой или связи нет."""


def save_portal(session: Session, domain: str, access_token: str,
                refresh_token: str = "", member_id: str = "") -> Portal:
    """Запоминает портал и свежие токены. Повторная установка обновляет запись."""
    portal = session.scalar(select(Portal).where(Portal.domain == domain))
    if portal is None:
        portal = Portal(domain=domain)
        session.add(portal)
    portal.access_token = access_token
    portal.refresh_token = refresh_token or portal.refresh_token
    portal.member_id = member_id or portal.member_id
    session.commit()
    return portal


def active_portal(session: Session) -> Portal | None:
    return session.scalars(select(Portal).order_by(Portal.installed_at.desc())).first()


def call(portal: Portal, method: str, params: dict | None = None) -> dict:
    """Вызов метода REST. Возвращает содержимое поля result."""
    url = f"https://{portal.domain}/rest/{method}"
    payload = dict(params or {}, auth=portal.access_token)
    try:
        response = httpx.post(url, data=payload, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise BitrixError(f"Портал недоступен: {exc}") from exc
    data = response.json()
    if "error" in data:
        raise BitrixError(data.get("error_description") or data["error"])
    return data.get("result", {})


def import_employees(session: Session) -> tuple[int, int]:
    """Тянет сотрудников портала в справочник.

    Возвращает пару «сколько добавлено, сколько уже было».
    Совпадение ищем по id пользователя в Битрикс24, поэтому повторный импорт
    не плодит дубли.
    """
    portal = active_portal(session)
    if portal is None:
        raise BitrixError("Приложение не установлено ни в один портал Битрикс24")

    users = call(portal, "user.get", {"FILTER[ACTIVE]": "Y"})
    if isinstance(users, dict):  # на некоторых порталах result приходит словарём
        users = list(users.values())

    added = skipped = 0
    for user in users:
        b24_id = str(user.get("ID"))
        exists = session.scalar(select(Employee).where(Employee.b24_user_id == b24_id))
        if exists:
            skipped += 1
            continue
        full_name = " ".join(
            part for part in (user.get("LAST_NAME"), user.get("NAME")) if part
        ).strip() or f"Сотрудник {b24_id}"
        if session.scalar(select(Employee).where(Employee.full_name == full_name)):
            full_name = f"{full_name} (Б24 {b24_id})"
        session.add(Employee(
            full_name=full_name,
            position=user.get("WORK_POSITION") or "",
            b24_user_id=b24_id,
        ))
        added += 1
    session.commit()
    return added, skipped
