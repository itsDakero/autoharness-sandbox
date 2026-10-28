"""Allowed tag values and validation of the vision model's reply (stdlib only)."""
import json

CATEGORIES = ["top", "bottom", "shoes", "outerwear", "dress", "accessory"]
COLOURS = ["black", "white", "grey", "navy", "blue", "green", "red", "pink",
           "yellow", "orange", "purple", "brown", "beige", "multi"]
SEASONS = ["spring", "summer", "autumn", "winter"]
STYLES = ["casual", "smart", "sport", "formal"]
RETIRE_REASONS = ["sold", "worn_out", "given_away"]


class TagError(ValueError):
    """The reply can't be used; the message is shown on /review."""


def json_schema():
    """JSON schema for Ollama's `format` field; enums come from the lists above."""
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "colours": {"type": "array", "items": {"type": "string", "enum": COLOURS},
                        "maxItems": 3},
            "seasons": {"type": "array", "items": {"type": "string", "enum": SEASONS}},
            "style": {"type": "string", "enum": STYLES},
            "brand": {"type": "string"},
        },
        "required": ["category", "colours", "seasons", "style"],
    }


def _pick(values, allowed, limit=None):
    out = []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return out
    for v in values:
        if isinstance(v, str):
            v = v.strip().lower()
            if v in allowed and v not in out:
                out.append(v)
    return out[:limit] if limit else out


def validate(data):
    """Clean a dict of tags. Values outside the lists are dropped; no valid category -> TagError."""
    if not isinstance(data, dict):
        raise TagError("model reply was not a JSON object")
    cat = data.get("category")
    cat = cat.strip().lower() if isinstance(cat, str) else None
    if cat not in CATEGORIES:
        raise TagError(f"model gave no valid category (got {cat!r})")
    style = data.get("style")
    style = style.strip().lower() if isinstance(style, str) else None
    brand = data.get("brand")
    brand = brand.strip()[:60] if isinstance(brand, str) else ""
    return {
        "category": cat,
        "colours": _pick(data.get("colours"), COLOURS, 3),
        "seasons": _pick(data.get("seasons"), SEASONS),
        "style": style if style in STYLES else None,
        "brand": brand,
    }


def parse_reply(text):
    """Turn the model's message content into clean tags, or raise TagError."""
    if not isinstance(text, str) or not text.strip():
        raise TagError("model returned an empty reply")
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    try:
        data = json.loads(s)
    except ValueError:
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b <= a:
            raise TagError("model reply was not JSON") from None
        try:
            data = json.loads(s[a:b + 1])
        except ValueError:
            raise TagError("model reply was not JSON") from None
    return validate(data)


PROMPT = ("This is a photo of one clothing item. Describe it for a wardrobe catalogue: "
          "category, 1-3 main colours, the seasons it suits, the style, and the brand only "
          "if a logo or label is clearly readable (else empty string). Reply with JSON only.")
