"""Canonical identity normalization shared by authentication flows."""
import unicodedata


def normalize_identifier(identifier: str) -> str:
    return unicodedata.normalize("NFKC", identifier).strip().casefold()
