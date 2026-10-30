
import pytest

from server import _authorize_owner


def test_employee_cannot_access_another_users_documents():
    """An employee must be denied access to another user's documents."""
    claims = {
        "sub": "employee-1",
        "role": "employee",
    }

    with pytest.raises(Exception, match="Access denied"):
        _authorize_owner(
            claims=claims,
            owner_id="admin-owner-1",
            tool="search_document",
        )


def test_employee_can_access_own_documents():
    """An employee may access their own documents."""
    claims = {
        "sub": "employee-1",
        "role": "employee",
    }

    _authorize_owner(
        claims=claims,
        owner_id="employee-1",
        tool="search_document",
    )


def test_admin_can_access_another_users_documents():
    """An admin may access another user's documents."""
    claims = {
        "sub": "admin-1",
        "role": "admin",
    }

    _authorize_owner(
        claims=claims,
        owner_id="employee-1",
        tool="search_document",
    )


def test_admin_is_denied_when_admin_access_is_disabled():
    """Admin access can be explicitly disabled for a tool."""
    claims = {
        "sub": "admin-1",
        "role": "admin",
    }

    with pytest.raises(Exception, match="Access denied"):
        _authorize_owner(
            claims=claims,
            owner_id="employee-1",
            tool="index_document",
            allow_admin=False,
        )
