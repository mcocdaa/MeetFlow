from typing import Any

from app.outcomes.models import Decision
from app.refs import user_ref


def serialize_columns(item: Any) -> dict[str, Any]:
    """Bare column projection shared by outcome and agenda responses."""
    return {
        column.name: getattr(item, column.name) for column in item.__table__.columns
    }


def serialize_outcome(item: Any) -> dict[str, Any]:
    result = serialize_columns(item)
    result["is_derived"] = item.source_agenda_item_id is not None
    if isinstance(item, Decision):
        result["reviewers"] = [
            {
                "user_id": row.user_id,
                "status": row.status,
                "responded_at": row.responded_at,
                "comment": row.comment,
            }
            for row in item.reviewers
        ]
    return result


def decision_detail(item: Decision) -> dict[str, Any]:
    result = serialize_outcome(item)
    result["created_by_user_id"] = item.created_by
    result["created_by"] = user_ref(item.creator)
    result["decided_by"] = user_ref(item.decided_by)
    result["reviewers"] = [
        {
            "user_id": row.user_id,
            "user": user_ref(row.user),
            "status": row.status,
            "responded_at": row.responded_at,
            "comment": row.comment,
        }
        for row in item.reviewers
    ]
    return result


def action_detail(item) -> dict[str, Any]:
    result = serialize_outcome(item)
    result["created_by_user_id"] = item.created_by
    result["created_by"] = user_ref(item.creator)
    result["owner"] = user_ref(item.owner_user)
    return result


def question_detail(item) -> dict[str, Any]:
    result = serialize_outcome(item)
    result["created_by_user_id"] = item.created_by
    result["created_by"] = user_ref(item.creator)
    result["owner"] = user_ref(item.owner_user)
    return result
