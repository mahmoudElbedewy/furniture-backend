from __future__ import annotations

from typing import Any

from django.utils import timezone


MAX_PAGE_HISTORY = 24
MAX_RECENT_NAVIGATION = 12


def _text(value: Any, limit: int = 255) -> str:
    return str(value or "").strip()[:limit]


def _page_type(path: str, supplied_type: Any) -> str:
    allowed = {
        "catalog",
        "product",
        "category",
        "cart",
        "wishlist",
        "checkout",
        "orders",
        "track",
        "about",
        "auth",
        "admin",
        "other",
    }
    if supplied_type in allowed:
        return supplied_type
    if path.startswith("/product/"):
        return "product"
    if path.startswith("/category/"):
        return "category"
    if path.startswith("/cart"):
        return "cart"
    if path.startswith("/wishlist"):
        return "wishlist"
    if path in {"/", "/products"}:
        return "catalog"
    return "other"


def normalize_browsing_event(raw_context: Any) -> dict[str, str] | None:
    if not isinstance(raw_context, dict):
        return None

    current_page = _text(raw_context.get("current_page"), 500)
    if not current_page or not current_page.startswith("/"):
        return None

    event = {
        "current_page": current_page,
        "page_type": _page_type(current_page, raw_context.get("page_type")),
        "visited_at": timezone.now().isoformat(),
    }
    for key in ("product_id", "product_slug", "product_name", "category_name"):
        value = _text(raw_context.get(key))
        if value:
            event[key] = value
    return event


def _event_key(event: dict[str, str]) -> tuple[str, str, str]:
    return (
        event.get("current_page", ""),
        event.get("page_type", ""),
        event.get("product_id", ""),
    )


def update_conversation_browsing_context(conversation, raw_context: Any) -> bool:
    """Store a compact, server-sanitized navigation trail without touching chat recency."""
    current_event = normalize_browsing_event(raw_context)
    if not current_event:
        return False

    existing_history = conversation.page_history if isinstance(conversation.page_history, list) else []
    history = [item for item in existing_history if isinstance(item, dict)]

    provided_history = raw_context.get("recent_navigation", []) if isinstance(raw_context, dict) else []
    provided_events: list[dict[str, str]] = []
    if isinstance(provided_history, list):
        for item in provided_history[-MAX_RECENT_NAVIGATION:]:
            event = normalize_browsing_event(item)
            if event:
                provided_events.append(event)

    overlap = 0
    for size in range(1, min(len(history), len(provided_events)) + 1):
        if [
            _event_key(event) for event in history[-size:]
        ] == [_event_key(event) for event in provided_events[:size]]:
            overlap = size
    history.extend(provided_events[overlap:])

    history.append(current_event)
    compact_history: list[dict[str, str]] = []
    for event in history:
        if compact_history and _event_key(compact_history[-1]) == _event_key(event):
            compact_history[-1] = event
        else:
            compact_history.append(event)

    conversation.last_page_context = current_event
    conversation.page_history = compact_history[-MAX_PAGE_HISTORY:]
    conversation.context_updated_at = timezone.now()
    conversation.save(
        update_fields=["last_page_context", "page_history", "context_updated_at"]
    )
    return True
