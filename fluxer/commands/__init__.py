"""Command system for fluxer.py bots."""

from .cog import Cog
from .checks import has_role, has_permission

__all__ = [
    "Cog",
    "has_role",
    "has_permission",
]
