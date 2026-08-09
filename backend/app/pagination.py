def slice_page(rows: list, *, limit: int) -> tuple[list, int | None, bool]:
    """Slice limit+1-fetched rows into items, next-cursor and has-more."""
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None
    return items, next_cursor, has_more
