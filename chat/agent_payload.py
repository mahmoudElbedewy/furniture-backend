import re


PRODUCT_CARDS_PATTERN = re.compile(r"\s*\[\[PRODUCT_CARDS:([a-f0-9,\-]+)\]\]\s*", re.IGNORECASE)


def split_agent_payload(content: str) -> tuple[str, dict]:
    """Remove agent control markers from chat text and expose UI metadata."""
    text = content or ""
    match = PRODUCT_CARDS_PATTERN.search(text)
    metadata = {}
    if match:
        ids = [item for item in match.group(1).split(",") if item]
        metadata["product_cards"] = {
            "ids": ids,
            "api_endpoint": f"/api/catalog/product-cards/?ids={','.join(ids)}",
        }
        text = PRODUCT_CARDS_PATTERN.sub("", text).strip()
    return text, metadata
