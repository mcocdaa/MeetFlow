from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.models import AgendaItem
from app.auth.models import User, UserRole, UserStatus
from app.collaboration.activity import ActivityRecorder
from app.collaboration.models import Comment, CommentMention
from app.collaboration.schemas import CommentCommand, CommentEdit, CommentWrite
from app.domain.versioning import require_version
from app.errors import AppError
from app.inbox.service import NotificationWriter
from app.meetings.models import Meeting, MeetingParticipant
from app.outcomes.models import ActionItem, Decision
from app.projects.access import WorkspaceAccess
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


def comment_options():
    return (
        joinedload(Comment.creator),
        joinedload(Comment.resolver),
        selectinload(Comment.mentions).joinedload(CommentMention.user),
    )


@dataclass(frozen=True)
class CommentThreadPage:
    items: list[Comment]
    replies_by_parent: dict[str, list[Comment]]
    reply_next_cursor_by_parent: dict[str, str | None]
    next_cursor: str | None
    can_change: bool = False


@dataclass(frozen=True)
class CommentReplyPage:
    items: list[Comment]
    next_cursor: str | None
    can_change: bool = False


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

    def _require_comment_access(
        self, project_id: str, meeting_id: str | None, actor: User
    ) -> None:
        access = WorkspaceAccess(self.session)
        if meeting_id is None:
            access.require_project_contribute(project_id, actor)
        else:
            access.require_meeting_comment(meeting_id, actor)

    def _mentions(
        self, user_ids: list[str], actor: User, meeting_id: str | None
    ) -> list[CommentMention]:
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
        if meeting_id is not None:
            participant_ids = set(
                self.session.scalars(
                    select(MeetingParticipant.user_id).where(
                        MeetingParticipant.meeting_id == meeting_id
                    )
                )
            )
            not_participants = [
                user_id for user_id in ids if user_id not in participant_ids
            ]
            if not_participants:
                raise AppError(
                    422,
                    "comment_mention_not_participant",
                    "评论只能提及会议参与者",
                    details={"user_ids": not_participants},
                )
        return [CommentMention(user_id=user_id) for user_id in ids]

    @staticmethod
    def _require_thread_owner_or_admin(comment: Comment, actor: User) -> None:
        if comment.created_by != actor.id and actor.role != UserRole.ADMIN:
            raise AppError(403, "comment_resolve_forbidden", "只能解决自己的评论")

    def _get_loaded(self, comment_id: str) -> Comment:
        comment = self.session.scalar(
            select(Comment)
            .where(Comment.id == comment_id)
            .options(*comment_options())
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
        self._require_comment_access(project_id, meeting_id, actor)
        parent_id = None
        direct_parent_id = None
        direct_recipient = None
        if payload.parent_id is not None:
            direct_parent = self._get_loaded(payload.parent_id)
            if (
                direct_parent.target_type != payload.target_type
                or direct_parent.target_id != payload.target_id
            ):
                raise AppError(
                    422,
                    "comment_parent_mismatch",
                    "回复必须属于同一评论目标",
                )
            direct_parent_id = direct_parent.id
            direct_recipient = direct_parent.created_by
            parent_id = direct_parent.parent_id or direct_parent.id
        mentions = self._mentions(payload.mention_user_ids, actor, meeting_id)
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
            writer = NotificationWriter(self.session)
            for mention in mentions:
                writer.add(
                    user_id=mention.user_id,
                    actor_user_id=actor.id,
                    project_id=comment.project_id,
                    meeting_id=comment.meeting_id,
                    kind="comment.mention",
                    subject_type=comment.target_type,
                    subject_id=comment.target_id,
                    source_comment_id=comment.id,
                    data={
                        "target_type": comment.target_type,
                        "target_id": comment.target_id,
                        "version": comment.version,
                    },
                    dedupe_key=(
                        f"mention:{comment.id}:{mention.user_id}:{comment.version}"
                    ),
                )
            if direct_recipient is not None:
                writer.add(
                    user_id=direct_recipient,
                    actor_user_id=actor.id,
                    project_id=comment.project_id,
                    meeting_id=comment.meeting_id,
                    kind="comment.reply",
                    subject_type=comment.target_type,
                    subject_id=comment.target_id,
                    source_comment_id=comment.id,
                    data={
                        "target_type": comment.target_type,
                        "target_id": comment.target_id,
                        "parent_id": parent_id,
                        "replied_to_comment_id": direct_parent_id,
                    },
                    dedupe_key=f"reply:{comment.id}:{direct_recipient}",
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._get_loaded(comment_id)

    def update(self, comment_id: str, payload: CommentEdit, actor: User) -> Comment:
        self._require_active(actor)
        comment = self._get_loaded(comment_id)
        self._require_comment_access(comment.project_id, comment.meeting_id, actor)
        if comment.created_by != actor.id and actor.role != UserRole.ADMIN:
            raise AppError(403, "comment_edit_forbidden", "只能编辑自己的评论")
        require_version(payload.expected_version, comment.version)
        if comment.deleted_at is not None:
            raise AppError(409, "comment_deleted", "已删除评论不可编辑")
        existing_mention_ids = {row.user_id for row in comment.mentions}
        mentions = self._mentions(payload.mention_user_ids, actor, comment.meeting_id)
        comment.body_markdown = payload.body_markdown
        comment.mentions = mentions
        comment.edited_at = utcnow()
        comment.version += 1
        self._record(comment, actor, "comment.updated")
        writer = NotificationWriter(self.session)
        for mention in mentions:
            if mention.user_id not in existing_mention_ids:
                writer.add(
                    user_id=mention.user_id,
                    actor_user_id=actor.id,
                    project_id=comment.project_id,
                    meeting_id=comment.meeting_id,
                    kind="comment.mention",
                    subject_type=comment.target_type,
                    subject_id=comment.target_id,
                    source_comment_id=comment.id,
                    data={
                        "target_type": comment.target_type,
                        "target_id": comment.target_id,
                        "version": comment.version,
                    },
                    dedupe_key=(
                        f"mention:{comment.id}:{mention.user_id}:{comment.version}"
                    ),
                )
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
        self._require_comment_access(comment.project_id, comment.meeting_id, actor)
        if comment.created_by != actor.id and actor.role != UserRole.ADMIN:
            raise AppError(403, "comment_delete_forbidden", "只能删除自己的评论")
        if comment.deleted_at is not None:
            if payload.expected_version in {comment.version, comment.version - 1}:
                return comment
            require_version(payload.expected_version, comment.version)
        else:
            require_version(payload.expected_version, comment.version)
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

    def resolve(self, comment_id: str, payload: CommentCommand, actor: User) -> Comment:
        self._require_active(actor)
        comment = self._get_loaded(comment_id)
        self._require_comment_access(comment.project_id, comment.meeting_id, actor)
        if comment.parent_id is not None:
            raise AppError(422, "comment_root_required", "只能解决评论主题")
        self._require_thread_owner_or_admin(comment, actor)
        require_version(payload.expected_version, comment.version)
        if comment.deleted_at is not None:
            raise AppError(409, "comment_deleted", "已删除评论不可解决")
        if comment.resolved_at is not None:
            return comment
        comment.resolved_at = utcnow()
        comment.resolved_by = actor.id
        comment.version += 1
        self._record(comment, actor, "comment.resolved")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_stale(comment_id, payload.expected_version, exc)
        except Exception:
            self.session.rollback()
            raise
        return self._get_loaded(comment_id)

    def reopen(self, comment_id: str, payload: CommentCommand, actor: User) -> Comment:
        self._require_active(actor)
        comment = self._get_loaded(comment_id)
        self._require_comment_access(comment.project_id, comment.meeting_id, actor)
        if comment.parent_id is not None:
            raise AppError(422, "comment_root_required", "只能重开评论主题")
        self._require_thread_owner_or_admin(comment, actor)
        require_version(payload.expected_version, comment.version)
        if comment.deleted_at is not None:
            raise AppError(409, "comment_deleted", "已删除评论不可重开")
        if comment.resolved_at is None:
            return comment
        comment.resolved_at = None
        comment.resolved_by = None
        comment.version += 1
        self._record(comment, actor, "comment.reopened")
        try:
            self.session.commit()
        except StaleDataError as exc:
            self._raise_stale(comment_id, payload.expected_version, exc)
        except Exception:
            self.session.rollback()
            raise
        return self._get_loaded(comment_id)

    def list_for_target(
        self,
        target_type: str,
        target_id: str,
        *,
        actor: User | None = None,
        before: str | None = None,
        limit: int = 20,
        reply_limit: int = 50,
    ) -> CommentThreadPage:
        project_id, meeting_id = self._target_context(target_type, target_id)
        can_change = False
        if actor is not None:
            access = WorkspaceAccess(self.session)
            if meeting_id is None:
                _, capabilities = access.require_project_view_with_capabilities(
                    project_id, actor
                )
                can_change = capabilities.can_contribute
            else:
                _, capabilities = access.require_meeting_view_with_capabilities(
                    meeting_id, actor
                )
                can_change = capabilities.can_comment
        filters = [
            Comment.target_type == target_type,
            Comment.target_id == target_id,
            Comment.parent_id.is_(None),
        ]
        if before is not None:
            cursor = self.session.get(Comment, before)
            if (
                cursor is None
                or cursor.target_type != target_type
                or cursor.target_id != target_id
                or cursor.parent_id is not None
            ):
                raise AppError(422, "invalid_comment_cursor", "评论游标无效")
            filters.append(
                or_(
                    Comment.created_at < cursor.created_at,
                    and_(
                        Comment.created_at == cursor.created_at,
                        Comment.id < cursor.id,
                    ),
                )
            )
        roots = list(
            self.session.scalars(
                select(Comment)
                .where(*filters)
                .options(*comment_options())
                .order_by(Comment.created_at.desc(), Comment.id.desc())
                .limit(limit + 1)
            )
        )
        has_more = len(roots) > limit
        items = roots[:limit]
        next_cursor = items[-1].id if has_more and items else None
        reply_rows_by_parent = {item.id: [] for item in items}
        root_ids = [item.id for item in items]
        if root_ids:
            ranked_replies = (
                select(
                    Comment.id.label("comment_id"),
                    func.row_number()
                    .over(
                        partition_by=Comment.parent_id,
                        order_by=(Comment.created_at.asc(), Comment.id.asc()),
                    )
                    .label("reply_number"),
                )
                .where(Comment.parent_id.in_(root_ids))
                .subquery()
            )
            replies = self.session.scalars(
                select(Comment)
                .join(
                    ranked_replies,
                    ranked_replies.c.comment_id == Comment.id,
                )
                .where(ranked_replies.c.reply_number <= reply_limit + 1)
                .options(*comment_options())
                .order_by(Comment.parent_id, Comment.created_at, Comment.id)
            )
            for reply in replies:
                reply_rows_by_parent[reply.parent_id].append(reply)
        replies_by_parent = {}
        reply_next_cursor_by_parent = {}
        for root_id, rows in reply_rows_by_parent.items():
            has_more_replies = len(rows) > reply_limit
            replies_by_parent[root_id] = rows[:reply_limit]
            reply_next_cursor_by_parent[root_id] = (
                replies_by_parent[root_id][-1].id
                if has_more_replies and replies_by_parent[root_id]
                else None
            )
        return CommentThreadPage(
            items=items,
            replies_by_parent=replies_by_parent,
            reply_next_cursor_by_parent=reply_next_cursor_by_parent,
            next_cursor=next_cursor,
            can_change=can_change,
        )

    def list_replies(
        self,
        root_id: str,
        *,
        actor: User | None = None,
        after: str | None = None,
        limit: int = 50,
    ) -> CommentReplyPage:
        root = self._get_loaded(root_id)
        can_change = False
        if actor is not None:
            access = WorkspaceAccess(self.session)
            if root.meeting_id is None:
                _, capabilities = access.require_project_view_with_capabilities(
                    root.project_id, actor
                )
                can_change = capabilities.can_contribute
            else:
                _, capabilities = access.require_meeting_view_with_capabilities(
                    root.meeting_id, actor
                )
                can_change = capabilities.can_comment
        if root.parent_id is not None:
            raise AppError(422, "comment_root_required", "只能分页读取根评论的回复")
        filters = [Comment.parent_id == root.id]
        if after is not None:
            cursor = self.session.get(Comment, after)
            if cursor is None or cursor.parent_id != root.id:
                raise AppError(422, "invalid_comment_cursor", "评论游标无效")
            filters.append(
                or_(
                    Comment.created_at > cursor.created_at,
                    and_(
                        Comment.created_at == cursor.created_at,
                        Comment.id > cursor.id,
                    ),
                )
            )
        rows = list(
            self.session.scalars(
                select(Comment)
                .where(*filters)
                .options(*comment_options())
                .order_by(Comment.created_at, Comment.id)
                .limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        return CommentReplyPage(
            items=items,
            next_cursor=items[-1].id if has_more and items else None,
            can_change=can_change,
        )

    def serialize(
        self,
        comment: Comment,
        actor: User,
        *,
        can_change: bool = False,
        replies: list[Comment] | None = None,
        reply_next_cursor: str | None = None,
    ) -> dict[str, Any]:
        comment_can_change = (
            (comment.created_by == actor.id or actor.role == UserRole.ADMIN)
            and can_change
        )
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
            "resolved_at": comment.resolved_at,
            "resolved_by": user_ref(comment.resolver) if comment.resolver else None,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "can_edit": comment_can_change and comment.deleted_at is None,
            "can_delete": comment_can_change,
            "can_resolve": (
                comment_can_change
                and comment.parent_id is None
                and comment.deleted_at is None
            ),
            "replies": [],
            "reply_next_cursor": reply_next_cursor,
        }
        if replies is not None:
            result["replies"] = [
                self.serialize(reply, actor, can_change=can_change) for reply in replies
            ]
        return result
