from typing import Any

from sqlalchemy.orm import Session

from app.workspace.models import UserWorkBrief


def current_work_brief(session: Session, user_id: str) -> dict[str, Any]:
    brief = session.get(UserWorkBrief, user_id)
    return {
        "content_markdown": brief.content_markdown if brief else "",
        "generated_at": brief.generated_at if brief else None,
    }


def replace_work_brief(
    session: Session, user_id: str, content_markdown: str
) -> dict[str, Any]:
    brief = session.get(UserWorkBrief, user_id)
    if brief is None:
        brief = UserWorkBrief(user_id=user_id, content_markdown=content_markdown)
        session.add(brief)
    else:
        brief.content_markdown = content_markdown
    session.commit()
    session.refresh(brief)
    return current_work_brief(session, user_id)
