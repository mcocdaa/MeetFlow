from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.errors import AppError
from app.meetings.models import ActionItem, Attachment, Meeting, MeetingUpdate
from app.meetings.schemas import ActionWrite, MeetingWrite, UpdateWrite


def actor_dict(user: User) -> dict[str, str]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


def conclusion_count(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if line.strip())


class MeetingService:
    def __init__(self, session: Session):
        self.session = session

    def require(self, meeting_id: str) -> Meeting:
        meeting = self.session.get(Meeting, meeting_id)
        if not meeting:
            raise AppError(404, "meeting_not_found", "会议不存在")
        return meeting

    def _actor(self, user_id: str) -> dict[str, str]:
        user = self.session.get(User, user_id)
        if not user:
            raise AppError(500, "actor_not_found", "会议创建者不存在")
        return actor_dict(user)

    def serialize(self, meeting: Meeting) -> dict[str, Any]:
        return {
            "id": meeting.id,
            "title": meeting.title,
            "project": meeting.project,
            "meeting_type": meeting.meeting_type,
            "meeting_date": meeting.meeting_date,
            "participants": meeting.participants,
            "raw_notes_markdown": meeting.raw_notes_markdown,
            "conclusions_markdown": meeting.conclusions_markdown,
            "created_by": self._actor(meeting.created_by),
            "updated_by": self._actor(meeting.updated_by),
            "created_at": meeting.created_at,
            "updated_at": meeting.updated_at,
        }

    def create(self, payload: MeetingWrite, user: User) -> dict[str, Any]:
        meeting = Meeting(
            **payload.model_dump(), created_by=user.id, updated_by=user.id
        )
        self.session.add(meeting)
        self.session.commit()
        self.session.refresh(meeting)
        return self.serialize(meeting)

    def update(
        self, meeting_id: str, payload: MeetingWrite, user: User
    ) -> dict[str, Any]:
        meeting = self.require(meeting_id)
        for field, value in payload.model_dump().items():
            setattr(meeting, field, value)
        meeting.updated_by = user.id
        self.session.commit()
        self.session.refresh(meeting)
        return self.serialize(meeting)

    def delete(self, meeting_id: str) -> None:
        meeting = self.require(meeting_id)
        self.session.delete(meeting)
        self.session.commit()

    def list_meetings(self, query: str = "") -> list[dict[str, Any]]:
        statement = select(Meeting).order_by(Meeting.meeting_date.desc())
        normalized = query.strip().casefold()
        if normalized:
            pattern = f"%{normalized}%"
            statement = statement.where(
                or_(
                    func.lower(Meeting.title).like(pattern),
                    func.lower(Meeting.project).like(pattern),
                )
            )

        results = []
        for meeting in self.session.scalars(statement):
            item = self.serialize(meeting)
            open_actions = self.session.scalar(
                select(func.count(ActionItem.id)).where(
                    ActionItem.meeting_id == meeting.id,
                    ActionItem.status == "open",
                )
            )
            attachments = self.session.scalar(
                select(func.count(Attachment.id)).where(
                    Attachment.meeting_id == meeting.id
                )
            )
            item.update(
                {
                    "conclusion_count": conclusion_count(
                        meeting.conclusions_markdown
                    ),
                    "open_action_count": open_actions or 0,
                    "attachment_count": attachments or 0,
                }
            )
            results.append(item)
        return results

    def package(self, meeting_id: str) -> dict[str, Any]:
        package = self.serialize(self.require(meeting_id))
        actions = self.session.scalars(
            select(ActionItem)
            .where(ActionItem.meeting_id == meeting_id)
            .order_by(ActionItem.created_at)
        )
        updates = self.session.scalars(
            select(MeetingUpdate)
            .where(MeetingUpdate.meeting_id == meeting_id)
            .order_by(MeetingUpdate.created_at.desc())
        )
        attachments = self.session.scalars(
            select(Attachment)
            .where(Attachment.meeting_id == meeting_id)
            .order_by(Attachment.created_at.desc())
        )
        package.update(
            {
                "actions": [self.serialize_action(item) for item in actions],
                "attachments": [
                    self.serialize_attachment(item) for item in attachments
                ],
                "updates": [self.serialize_update(item) for item in updates],
            }
        )
        return package

    def serialize_attachment(self, item: Attachment) -> dict[str, Any]:
        return {
            "id": item.id,
            "meeting_id": item.meeting_id,
            "original_name": item.original_name,
            "mime_type": item.mime_type,
            "size": item.size,
            "attachment_type": item.attachment_type,
            "created_by": self._actor(item.created_by),
            "created_at": item.created_at,
            "download_url": (
                f"/api/meetings/{item.meeting_id}/attachments/{item.id}"
            ),
        }

    def serialize_action(self, item: ActionItem) -> dict[str, Any]:
        meeting = self.require(item.meeting_id)
        return {
            "id": item.id,
            "meeting_id": item.meeting_id,
            "meeting_title": meeting.title,
            "content": item.content,
            "owner": item.owner,
            "due_date": item.due_date,
            "status": item.status,
            "created_by": self._actor(item.created_by),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def require_action(self, meeting_id: str, action_id: str) -> ActionItem:
        item = self.session.scalar(
            select(ActionItem).where(
                ActionItem.id == action_id,
                ActionItem.meeting_id == meeting_id,
            )
        )
        if not item:
            raise AppError(404, "action_not_found", "行动项不存在")
        return item

    def create_action(
        self, meeting_id: str, payload: ActionWrite, user: User
    ) -> dict[str, Any]:
        self.require(meeting_id)
        item = ActionItem(
            meeting_id=meeting_id,
            created_by=user.id,
            **payload.model_dump(),
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return self.serialize_action(item)

    def update_action(
        self,
        meeting_id: str,
        action_id: str,
        payload: ActionWrite,
    ) -> dict[str, Any]:
        item = self.require_action(meeting_id, action_id)
        for field, value in payload.model_dump().items():
            setattr(item, field, value)
        self.session.commit()
        self.session.refresh(item)
        return self.serialize_action(item)

    def delete_action(self, meeting_id: str, action_id: str) -> None:
        item = self.require_action(meeting_id, action_id)
        self.session.delete(item)
        self.session.commit()

    def list_actions(self, status: str) -> list[dict[str, Any]]:
        statement = select(ActionItem).order_by(
            ActionItem.due_date.asc(), ActionItem.created_at.desc()
        )
        if status:
            statement = statement.where(ActionItem.status == status)
        return [self.serialize_action(item) for item in self.session.scalars(statement)]

    def serialize_update(self, item: MeetingUpdate) -> dict[str, Any]:
        return {
            "id": item.id,
            "meeting_id": item.meeting_id,
            "content_markdown": item.content_markdown,
            "created_by": self._actor(item.created_by),
            "created_at": item.created_at,
        }

    def create_update(
        self, meeting_id: str, payload: UpdateWrite, user: User
    ) -> dict[str, Any]:
        self.require(meeting_id)
        item = MeetingUpdate(
            meeting_id=meeting_id,
            created_by=user.id,
            content_markdown=payload.content_markdown,
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return self.serialize_update(item)

    def delete_update(self, meeting_id: str, update_id: str) -> None:
        item = self.session.scalar(
            select(MeetingUpdate).where(
                MeetingUpdate.id == update_id,
                MeetingUpdate.meeting_id == meeting_id,
            )
        )
        if not item:
            raise AppError(404, "update_not_found", "补充记录不存在")
        self.session.delete(item)
        self.session.commit()

    def plugin_context(self, meeting_id: str, user: User) -> dict[str, Any]:
        package = self.package(meeting_id)
        return {
            "id": package["id"],
            "title": package["title"],
            "project": package["project"],
            "meeting_type": package["meeting_type"],
            "meeting_date": package["meeting_date"],
            "participants": package["participants"],
            "raw_notes_markdown": package["raw_notes_markdown"],
            "conclusions_markdown": package["conclusions_markdown"],
            "actions": package["actions"],
            "updates": package["updates"],
            "attachments": [
                {
                    "id": item["id"],
                    "original_name": item["original_name"],
                    "mime_type": item["mime_type"],
                    "size": item["size"],
                    "attachment_type": item["attachment_type"],
                }
                for item in package["attachments"]
            ],
            "current_user": actor_dict(user),
        }
