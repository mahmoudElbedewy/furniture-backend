"""Shared, privacy-preserving visitor keys for storefront analytics."""

from hashlib import sha256

from agent.models import FunnelEvent


def visitor_session_key(request):
    """Return a stable anonymous key without storing the raw browser identifier."""
    visitor_id = (request.headers.get("X-Furniture-Visitor") or "").strip()
    if visitor_id:
        source = f"visitor:{visitor_id[:128]}"
    else:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip_address = (forwarded_for.split(",")[0] if forwarded_for else request.META.get("REMOTE_ADDR", "")).strip()
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        source = f"fallback:{ip_address}:{user_agent}"
    return sha256(source.encode("utf-8")).hexdigest()[:32]


def record_funnel_event(request, event_type, *, product=None, order=None):
    """Record a single funnel event using the same key in browser and order flows."""
    return FunnelEvent.objects.create(
        event_type=event_type,
        session_key=visitor_session_key(request),
        product=product,
        order=order,
    )
