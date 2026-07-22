from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.models import AgendaItem
from app.auth.models import User, UserRole, UserStatus
from app.collaboration.activity import ActivityRecorder
from app.collaboration.models import Comment, CommentMention
from app.collaboration.schemas import CommentCommand, CommentEdit, CommentWrite
from app.domain.versioning import require_version
from app.errors import AppError
from app.meetings.models import Meeting
from app.outcomes.models import ActionItem, Decision
from app.projects.models import Project

SUPPORTED_TARGETS = {
    "project": Project,
    "meeting": Meeting,
    "agenda_item": AgendaItem,
    "decision": Decision,
    "action_item": ActionItem,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def user_ref(user: User) -> dict[str, str]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_color": user.avatar_color,
    }


def comment_options(*, include_replies: bool = False):
    options = [
        joinedload(Comment.creator),
        selectinload(Comment.mentions).joinedload(CommentMention.user),
    ]
    if include_replies:
        options.extend(
            [
                selectinload(Comment.replies).joinedload(Comment.creator),
                selectinload(Comment.replies)
                .selectinload(Comment.mentions)
                .joinedload(CommentMention.user),
            ]
        )
    return tuple(options)


class CommentService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _require_active(actor: User) -> None:
        if actor.status != UserStatus.ACTIVE:
            raise AppError(403, "active_user_required", "账号尚未启用")

    def _target_context(
        self, target_type: str, target_id: str
    ) -> tuple[str, str | None]:
        model = SUPPORTED_TARGETS.get(target_type)
        if model is None:
            raise AppError(422, "unsupported_comment_target", "不支持此评论目标")
        target = self.session.get(model, target_id)
        if target is None:
            raise AppError(404, "comment_target_not_found", "评论目标不存在")
        if isinstance(target, Project):
            return target.id, None
        if isinstance(target, Meeting):
            return target.project_id, target.id
        if isinstance(target, AgendaItem):
            meeting = target.meeting
            return meeting.project_id, meeting.id
        return target.project_id, target.meeting_id

    def _mentions(self, user_ids: list[str], actor: User) -> list[CommentMention]:
        ids = list(
            dict.fromkeys(user_id for user_id in user_ids if user_id != actor.id)
        )
        if not ids:
            return []
        users = {
            user.id: user
            for user in self.session.scalars(select(User).where(User.id.in_(ids)))
        }
        invalid = [
            user_id
            for user_id in ids
            if user_id not in users or users[user_id].status != UserStatus.ACTIVE
        ]
        if invalid:
            raise AppError(
                422,
                "comment_mention_user_invalid",
                "评论提及用户不存在或未启用",
                details={"user_ids": invalid},
            )
        return [CommentMention(user_id=user_id) for user_id in ids]

    def _get_loaded(self, comment_id: str, *, include_replies: bool = False) -> Comment:
        comment = self.session.scalar(
            select(Comment)
            .where(Comment.id == comment_id)
            .options(*comment_options(include_replies=include_replies))
            .execution_options(populate_existing=True)
        )
        if comment is None:
            raise AppError(404, "comment_not_found", "评论不存在")
        return comment

    def _record(self, comment: Comment, actor: User, event_type: str) -> None:
        ActivityRecorder(self.session).record(
            project_id=comment.project_id,
            meeting_id=comment.meeting_id,
            actor_user_id=actor.id,
            event_type=event_type,
            subject_type="comment",
            subject_id=comment.id,
            payload={
                "target_type": comment.target_type,
                "target_id": comment.target_id,
                "parent_id": comment.parent_id,
            },
        )

    def _raise_stale(
        self, comment_id: str, expected_version: int, exc: Exception
    ) -> None:
        self.session.rollback()
        actual = self.session.scalar(
            select(Comment.version).where(Comment.id == comment_id)
        )
        if actual is None:
            raise AppError(404, "comment_not_found", "评论不存在") from exc
        require_version(expected_version, actual)
        raise AppError(
            409,
            "version_conflict",
            "评论已被其他操作更新，请刷新后重试",
            details={
                "expected_version": expected_version,
                "actual_version": actual,
            },
        ) from exc

    def create(self, payload: CommentWrite, actor: User) -> Comment:
        self._require_active(actor)
        project_id, meeting_id = self._target_context(
            payload.target_type, payload.target_id
        )
        parent_id = None
        if payload.parent_id is not None:
            parent = self._get_loaded(payload.parent_id)
            if (
                parent.target_type != payload.target_type
                or parent.target_id != payload.target_id
            ):
                raise AppError(
                    422,
                    "comment_parent_mismatch",
                    "回复必须属于同一评论目标",
                )
            parent_id = parent.parent_id or parent.id
        mentions = self._mentions(payload.mention_user_ids, actor)
        comment = Comment(
            project_id=project_id,
            meeting_id=meeting_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            parent_id=parent_id,
            body_markdown=payload.body_markdown,
            version=1,
            created_by=actor.id,
            mentions=mentions,
        )
        self.session.add(comment)
        try:
            self.session.flush()
            comment_id = comment.id
            self._record(
                comment,
                actor,
                "comment.replied" if parent_id is not None else "comment.created",
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._get_loaded(comment_id)

    def update(self, comment_id: str, payload: CommentEdit, actor: User) -> Comment:
        self._require_active(actor)
        comment = self._get_loaded(comment_id)
        if comment.created_by != actor.id and actor.role != UserRole.ADMIN:
            raise AppError(403, "comment_edit_forbidden", "只能编辑自己的评论")
        require_version(payload.expected_version, comment.version)
        if comment.deleted_at is not None:
            raise AppError(409, "comment_deleted", "已删除评论不可编辑")
        mentions = self._mentions(payload.mention_user_ids, actor)
        comment.body_markdown = payload.body_markdown
        comment.mentions = mentions
        comment.edited_at = utcnow()
        comment.version += 1
        self._record(comment, actor, "comment.updated")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_stale(comment_id, payload.expected_version, exc)
        except Exception:
            self.session.rollback()
            raise
        return self._get_loaded(comment_id)

    def delete(self, comment_id: str, payload: CommentCommand, actor: User) -> Comment:
        self._require_active(actor)
        comment = self._get_loaded(comment_id)
        if comment.created_by != actor.id and actor.role != UserRole.ADMIN:
            raise AppError(403, "comment_delete_forbidden", "只能删除自己的评论")
        require_version(payload.expected_version, comment.version)
        if comment.deleted_at is not None:
            return comment
        comment.body_markdown = None
        comment.mentions = []
        comment.deleted_at = utcnow()
        comment.version += 1
        self._record(comment, actor, "comment.deleted")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_stale(comment_id, payload.expected_version, exc)
        except Exception:
            self.session.rollback()
            raise
        return self._get_loaded(comment_id)

    def list_for_target(self, target_type: str, target_id: str) -> list[Comment]:
        self._target_context(target_type, target_id)
        return list(
            self.session.scalars(
                select(Comment)
                .where(
                    Comment.target_type == target_type,
                    Comment.target_id == target_id,
                    Comment.parent_id.is_(None),
                )
                .options(*comment_options(include_replies=True))
                .order_by(Comment.created_at, Comment.id)
            )
        )

    @staticmethod
    def serialize(
        comment: Comment, actor: User, *, include_replies: bool
    ) -> dict[str, Any]:
        can_change = comment.created_by == actor.id or actor.role == UserRole.ADMIN
        result = {
            "id": comment.id,
            "target": {"type": comment.target_type, "id": comment.target_id},
            "project": {"id": comment.project_id},
            "meeting": {"id": comment.meeting_id} if comment.meeting_id else None,
            "parent_id": comment.parent_id,
            "body_markdown": comment.body_markdown,
            "version": comment.version,
            "creator": user_ref(comment.creator),
            "mentions": [user_ref(row.user) for row in comment.mentions],
            "edited_at": comment.edited_at,
            "deleted_at": comment.deleted_at,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "can_edit": can_change and comment.deleted_at is None,
            "can_delete": can_change,
            "replies": [],
        }
        if include_replies:
            result["replies"] = [
                CommentService.serialize(reply, actor, include_replies=False)
                for reply in comment.replies
            ]
        return result
