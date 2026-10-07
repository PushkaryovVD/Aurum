"""Canonical identity normalization shared by authentication flows."""
import unicodedata


MAX_NORMALIZED_IDENTIFIER_LENGTH = 320
MAX_DISPLAY_NAME_LENGTH = 100


def is_strict_utf8(value: str) -> bool:
    """Reject values that cannot cross strict UTF-8 boundaries."""
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def is_safe_text(value: str, *, min_length: int = 0, max_length: int) -> bool:
    """Validate text before hashing, parsing, or crossing persistence boundaries."""
    return (
        min_length <= len(value) <= max_length
        and "\x00" not in value
        and is_strict_utf8(value)
    )


def normalize_identifier(identifier: str) -> str:
    return unicodedata.normalize("NFKC", identifier).strip().casefold()


def valid_normalized_identifier(identifier: str) -> str | None:
    """Return the canonical identifier only when it fits persistence bounds."""
    normalized = normalize_identifier(identifier)
    if (
        not normalized
        or not is_strict_utf8(normalized)
        or "\x00" in normalized
        or len(normalized) > MAX_NORMALIZED_IDENTIFIER_LENGTH
    ):
        return None
    return normalized


def valid_display_name(display_name: str) -> str | None:
    """Return a trimmed display name that PostgreSQL can persist safely."""
    normalized = display_name.strip()
    if (
        not normalized
        or not is_strict_utf8(normalized)
        or "\x00" in normalized
        or len(normalized) > MAX_DISPLAY_NAME_LENGTH
    ):
        return None
    return normalized
