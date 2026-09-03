from __future__ import annotations

from .models.member import GuildMember
from .models.voice import VoiceState

Member = GuildMember

__all__ = ("GuildMember", "Member", "VoiceState")
