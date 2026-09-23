"""Guild member display name and avatar precedence."""

import pytest

from fluxer.http import HTTPClient
from fluxer.member import Member
from fluxer.models.member import GuildMember


def member_with_assets(
    *, nick: str | None = None, global_name: str | None = None,
    guild_avatar: str | None = None, user_avatar: str | None = None,
) -> GuildMember:
    """Build a member with local service URL configuration and no network calls."""
    http = HTTPClient("test-token", api_url="https://api.example.test/v1")
    http._endpoints._values = {
        "media": "https://media.example.test",
        "static_cdn": "https://static.example.test",
    }
    return GuildMember.from_data(
        {
            "user": {
                "id": "42", "username": "account", "global_name": global_name,
                "avatar": user_avatar,
            },
            "guild_id": "99", "nick": nick, "avatar": guild_avatar,
        },
        http,
    )


@pytest.mark.parametrize(
    ("nick", "global_name", "expected"),
    [
        ("Guild Nick", "Global Name", "Guild Nick"),
        (None, "Global Name", "Global Name"),
        (None, None, "account"),
    ],
)
def test_member_display_name_precedence(
    nick: str | None, global_name: str | None, expected: str
) -> None:
    member = member_with_assets(nick=nick, global_name=global_name)
    assert member.display_name == expected
    assert isinstance(member, Member)


def test_member_id_matches_underlying_user_for_parsed_and_alias_models() -> None:
    member = member_with_assets()
    assert member.id == 42
    assert member.id == member.user.id
    assert isinstance(member, Member)


@pytest.mark.parametrize(
    ("guild_avatar", "user_avatar", "expected"),
    [
        (
            "a_guild_hash", "a_user_hash",
            "https://media.example.test/guilds/99/users/42/avatars/a_guild_hash.gif",
        ),
        (
            None, "a_user_hash",
            "https://media.example.test/avatars/42/a_user_hash.gif",
        ),
        (
            None, "user_hash",
            "https://media.example.test/avatars/42/user_hash.png",
        ),
        (None, None, "https://static.example.test/avatars/0.png"),
    ],
)
def test_member_display_avatar_precedence(
    guild_avatar: str | None, user_avatar: str | None, expected: str
) -> None:
    member = member_with_assets(
        guild_avatar=guild_avatar, user_avatar=user_avatar
    )
    assert member.display_avatar == expected
    assert member.display_avatar == (
        member.guild_avatar_url
        or member.user.avatar_url
        or member.user.default_avatar_url
    )
