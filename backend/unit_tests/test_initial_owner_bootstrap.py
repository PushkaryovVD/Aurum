"""Persistence contract for one-time first-owner initialization."""

import pytest

from app.api.routes.auth import parse_first_owner_payload
from app.models.auth import InitialOwnerBootstrap


def test_initial_owner_bootstrap_persists_only_a_single_code_hmac() -> None:
    columns = InitialOwnerBootstrap.__table__.c

    assert list(InitialOwnerBootstrap.__table__.primary_key.columns.keys()) == ["id"]
    assert columns["id"].nullable is False
    assert columns["code_hmac"].nullable is False
    assert columns["code_hmac"].type.length == 32
    assert columns["expires_at"].nullable is False
    assert "code" not in columns
    assert "secret" not in columns


@pytest.mark.parametrize(
    "payload",
    [
        {"bootstrap_code": "code", "identifier": "owner@example.com", "display_name": "Owner", "password": "short"},
        {"bootstrap_code": "code", "identifier": "owner@example.com", "display_name": "Owner", "password": "x" * 1025},
        {"bootstrap_code": "x" * 1025, "identifier": "owner@example.com", "display_name": "Owner", "password": "correct horse"},
        {"bootstrap_code": "code", "identifier": ["owner@example.com"], "display_name": "Owner", "password": "correct horse"},
    ],
)
def test_initial_owner_payload_rejects_invalid_values_without_schema_oracles(payload: dict[str, object]) -> None:
    assert parse_first_owner_payload(payload) is None


def test_initial_owner_payload_accepts_backend_password_minimum() -> None:
    payload = {
        "bootstrap_code": "code",
        "identifier": "owner@example.com",
        "display_name": "Owner",
        "password": "twelve-chars",
    }

    assert parse_first_owner_payload(payload) is not None


def test_initial_owner_payload_rejects_identifier_that_expands_past_database_limit() -> None:
    payload = {
        "bootstrap_code": "code",
        "identifier": "\ufb03" * 107,
        "display_name": "Owner",
        "password": "twelve-chars",
    }

    assert parse_first_owner_payload(payload) is None


@pytest.mark.parametrize(
    "override",
    [
        {"identifier": "owner\x00@example.com"},
        {"display_name": "Owner\x00Name"},
        {"bootstrap_code": "\ud800"},
        {"bootstrap_code": "\udfff"},
        {"identifier": "owner\ud800@example.com"},
        {"identifier": "owner\udfff@example.com"},
        {"display_name": "Owner\ud800Name"},
        {"display_name": "Owner\udfffName"},
        {"password": "valid-password\ud800"},
        {"password": "valid-password\udfff"},
    ],
)
def test_initial_owner_payload_rejects_non_utf8_text(
    override: dict[str, str],
) -> None:
    payload = {
        "bootstrap_code": "code",
        "identifier": "owner@example.com",
        "display_name": "Owner",
        "password": "twelve-chars",
        **override,
    }

    assert parse_first_owner_payload(payload) is None
