from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, joinedload

from app.errors import AppError
from app.inbox.models import Notification


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class InboxHistoryPage:
    items: list[Notification]
    next_cursor: int | None


@dataclass(frozen=True)
class InboxChangesPage:
    items: list[Notification]
    next_cursor: int
    has_more: bool


class NotificationWriter:
    def __init__(self, session: Session):
        self.session = session

    def add(
        self,
        *,
        user_id: str,
        actor_user_id: str | None,
        project_id: str | None,
        meeting_id: str | None,
        kind: str,
        subject_type: str,
        subject_id: str,
        source_comment_id: str | None,
        data: dict[str, Any],
        dedupe_key: str,
    ) -> Notification | None:
        if actor_user_id == user_id:
            return None
        statement = (
            sqlite_insert(Notification)
            .values(
                user_id=user_id,
                actor_user_id=actor_user_id,
                project_id=project_id,
                meeting_id=meeting_id,
                kind=kind,
                subject_type=subject_type,
                subject_id=subject_id,
                source_comment_id=source_comment_id,
                data_json=data,
                dedupe_key=dedupe_key,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
            .returning(Notification)
        )
        with self.session.no_autoflush:
            notification = self.session.scalars(statement).first()
            if notification is not None:
                return notification
            return self.session.scalar(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.dedupe_key == dedupe_key,
                )
            )


class InboxService:
    def __init__(self, session: Session):
        self.session = session

    def history(
        self, user_id: str, *, before: int | None = None, limit: int = 50
    ) -> InboxHistoryPage:
        filters = [Notification.user_id == user_id]
        if before is not None:
            filters.append(Notification.id < before)
        rows = list(
            self.session.scalars(
                select(Notification)
                .where(*filters)
                .options(joinedload(Notification.actor))
                .order_by(Notification.id.desc())
                .limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        return InboxHistoryPage(
            items=items,
            next_cursor=items[-1].id if has_more and items else None,
        )

    def changes(
        self, user_id: str, *, cursor: int = 0, limit: int = 50
    ) -> InboxChangesPage:
        rows = list(
            self.session.scalars(
                select(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.id > cursor,
                )
                .options(joinedload(Notification.actor))
                .order_by(Notification.id)
                .limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        return InboxChangesPage(
            items=items,
            next_cursor=items[-1].id if items else cursor,
            has_more=has_more,
        )

    def unread_count(self, user_id: str) -> int:
        return (
            self.session.scalar(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
            or 0
        )

    def read(self, notification_id: int, user_id: str) -> None:
        notification = self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        if notification is None:
            raise AppError(404, "notification_not_found", "通知不存在")
        if notification.read_at is None:
            notification.read_at = utcnow()
            self.session.commit()

    def read_all(self, user_id: str) -> None:
        self.session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=utcnow())
        )
        self.session.commit()

    @staticmethod
    def serialize(item: Notification) -> dict[str, Any]:
        actor = None
        if item.actor is not None:
            actor = {
                "id": item.actor.id,
                "username": item.actor.username,
                "display_name": item.actor.display_name,
                "avatar_color": item.actor.avatar_color,
            }
        return {
            "id": item.id,
            "actor": actor,
            "kind": item.kind,
            "subject": {"type": item.subject_type, "id": item.subject_id},
            "project": {"id": item.project_id} if item.project_id else None,
            "meeting": {"id": item.meeting_id} if item.meeting_id else None,
            "source_comment": (
                {"id": item.source_comment_id} if item.source_comment_id else None
            ),
            "data": item.data_json,
            "read_at": item.read_at,
            "created_at": item.created_at,
        }
