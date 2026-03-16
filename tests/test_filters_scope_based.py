"""Unit tests for scope_based_filter."""

import pytest

from stac_auth_proxy.filters.scope_based_item_filter import scope_based_filter

STAGING_FILTER = "properties._staging IS NULL"


@pytest.fixture
def filter_fn():
    """Default scope_based_filter instance."""
    return scope_based_filter()


@pytest.mark.asyncio
async def test_no_payload_returns_staging_filter(filter_fn):
    """Unauthenticated requests (no payload) should see only non-staging items."""
    result = await filter_fn({})
    assert result == STAGING_FILTER


@pytest.mark.asyncio
async def test_payload_no_roles_returns_staging_filter(filter_fn):
    """Authenticated user with no roles should still be filtered."""
    result = await filter_fn({"payload": {"sub": "user1"}})
    assert result == STAGING_FILTER


@pytest.mark.asyncio
async def test_payload_empty_roles_list_returns_staging_filter(filter_fn):
    """Authenticated user with empty roles list should still be filtered."""
    result = await filter_fn({"payload": {"_roles": []}})
    assert result == STAGING_FILTER


@pytest.mark.asyncio
async def test_payload_non_superuser_role_returns_staging_filter(filter_fn):
    """User with unrelated roles should still be filtered."""
    result = await filter_fn({"payload": {"_roles": ["read:stac", "write:stac"]}})
    assert result == STAGING_FILTER


@pytest.mark.asyncio
async def test_superuser_role_list_returns_none(filter_fn):
    """User with superuser role in a list should see all items."""
    result = await filter_fn({"payload": {"_roles": ["superuser"]}})
    assert result is None


@pytest.mark.asyncio
async def test_superuser_role_string_returns_none(filter_fn):
    """User with superuser role as a space-separated string should see all items."""
    result = await filter_fn({"payload": {"_roles": "superuser read:stac"}})
    assert result is None


@pytest.mark.asyncio
async def test_superuser_role_string_only_returns_none(filter_fn):
    """User with superuser as the only string role should see all items."""
    result = await filter_fn({"payload": {"_roles": "superuser"}})
    assert result is None


@pytest.mark.asyncio
async def test_custom_superuser_role():
    """Custom superuser_role parameter should be respected."""
    fn = scope_based_filter(superuser_role="admin")

    assert await fn({"payload": {"_roles": ["admin"]}}) is None
    assert await fn({"payload": {"_roles": ["superuser"]}}) == STAGING_FILTER


@pytest.mark.asyncio
async def test_superuser_mixed_with_other_roles_returns_none(filter_fn):
    """Superuser role among other roles should grant full access."""
    result = await filter_fn(
        {"payload": {"_roles": ["read:stac", "superuser", "write:stac"]}}
    )
    assert result is None
