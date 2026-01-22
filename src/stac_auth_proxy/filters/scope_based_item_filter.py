# my_filters.py
"""CQL2 filter based on user scopes."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def scope_based_filter(superuser_role: str = "superuser"):
    """
    CQL2 builder that filters items based on user roles.

    - Users with superuser role see everything
    - Other users only see items where _staging is omitted

    Args:
        superuser_role: Role that grants full access

    """

    async def filter_by_scope(ctx: dict[str, Any]) -> Optional[str]:
        """Generate CQL2 expression based on user scopes."""
        payload = ctx.get("payload")

        if payload:
            role_claim = payload.get("scope", [])
            roles = (
                role_claim.split() if isinstance(role_claim, str) else role_claim or []
            )

            if superuser_role in roles:
                logger.info("Superuser request")
                return None

        return "properties._staging IS NULL"

    return filter_by_scope
