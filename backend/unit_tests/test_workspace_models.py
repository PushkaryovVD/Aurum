"""ORM registration contract for the identity/workspace foundation."""
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base
import app.models  # noqa: F401 - imports every registered model
from app.core.config import Settings


def test_identity_workspace_models_are_registered_with_uuid_primary_keys():
    expected_tables = {"users", "workspaces", "workspace_memberships"}

    assert expected_tables <= set(Base.metadata.tables)
    for table_name in expected_tables:
        table = Base.metadata.tables[table_name]
        assert list(table.primary_key.columns.keys()) == ["id"]
        assert isinstance(table.c.id.type, UUID)


def test_workspace_membership_role_contract_is_registered():
    membership = Base.metadata.tables["workspace_memberships"]

    assert membership.c.role.type.enums == ["owner", "editor", "viewer"]


def test_application_auth_remains_disabled_by_default():
    assert Settings(_env_file=None).app_auth_required is False
