"""Role helpers and public types for fluxer.py.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from .models.role import Role


class RoleTags:
    """Import-compatible placeholder with no supported platform role-tag fields.

    Attributes:
        __dict__: Instance namespace retained for compatibility; no platform fields are defined.
    """

    pass


__all__ = ("Role", "RoleTags")
