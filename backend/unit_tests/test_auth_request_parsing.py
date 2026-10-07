"""Unit tests for bounded, strict authentication request parsing."""
import json

import pytest
from starlette.requests import Request

from app.api.routes.auth import read_auth_json
from app.api.routes.workspaces import parse_invitation_create
from app.models.workspace import WorkspaceRole


def _request(body: bytes, *, content_type: str = "application/json") -> Request:
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-type", content_type.encode("ascii"))],
        },
        receive,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
async def test_auth_json_rejects_non_utf8_json_encodings(encoding):
    body = json.dumps({"identifier": "owner@example.com", "password": "valid-password"}).encode(
        encoding
    )

    assert await read_auth_json(_request(body)) is None


@pytest.mark.asyncio
async def test_auth_json_accepts_strict_utf8_object():
    body = json.dumps({"identifier": "owner@example.com", "password": "valid-password"}).encode()

    assert await read_auth_json(_request(body)) == {
        "identifier": "owner@example.com",
        "password": "valid-password",
    }


@pytest.mark.asyncio
async def test_auth_json_rejects_integer_beyond_python_digit_limit():
    body = b'{"identifier":' + (b"1" * 5000) + b',"password":"valid-password"}'

    assert await read_auth_json(_request(body)) is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"recipient": 1, "role": "viewer"},
        {"recipient": "member@example.com", "role": "owner"},
        {"recipient": "member@example.com", "role": "viewer", "expires_in_seconds": True},
    ],
)
def test_invitation_create_parser_rejects_schema_failures(payload):
    assert parse_invitation_create(payload) is None


def test_invitation_create_parser_returns_typed_values():
    assert parse_invitation_create(
        {"recipient": "member@example.com", "role": "editor", "expires_in_seconds": 3600}
    ) == ("member@example.com", WorkspaceRole.EDITOR, 3600)
