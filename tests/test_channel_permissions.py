"""Guild-channel permission interface tests."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

import fluxer
from fluxer.http import HTTPClient


class PermissionHTTP:
    """Record permission mutations at the model boundary."""

    def __init__(self) -> None:
        self.edits: list[tuple[int, int, dict[str, Any]]] = []
        self.deletes: list[tuple[int, int]] = []

    async def edit_channel_permissions(
        self, channel_id: int, overwrite_id: int, **kwargs: Any
    ) -> None:
        """Record one overwrite write."""
        self.edits.append((channel_id, overwrite_id, kwargs))

    async def delete_channel_permissions(
        self, channel_id: int, overwrite_id: int
    ) -> None:
        """Record one overwrite deletion."""
        self.deletes.append((channel_id, overwrite_id))


def permission_guild(http: Any = None) -> fluxer.Guild:
    """Build a guild snapshot covering each permission precedence stage."""
    return fluxer.Guild.from_data(
        {
            "id": "10",
            "name": "Permissions",
            "owner_id": "100",
            "roles": [
                {"id": "10", "permissions": str(int(fluxer.Permissions.VIEW_CHANNEL))},
                {"id": "20", "permissions": str(int(fluxer.Permissions.SEND_MESSAGES))},
                {"id": "21", "permissions": str(int(fluxer.Permissions.ADMINISTRATOR))},
            ],
            "members": [
                {"user": {"id": "100"}, "roles": []},
                {"user": {"id": "200"}, "roles": ["20"]},
                {"user": {"id": "201"}, "roles": ["21"]},
            ],
            "channels": [
                {
                    "id": "30",
                    "type": 0,
                    "permission_overwrites": [
                        {
                            "id": "10",
                            "type": 0,
                            "allow": "0",
                            "deny": str(int(fluxer.Permissions.VIEW_CHANNEL)),
                        },
                        {
                            "id": "20",
                            "type": 0,
                            "allow": str(int(fluxer.Permissions.VIEW_CHANNEL)),
                            "deny": str(int(fluxer.Permissions.SEND_MESSAGES)),
                        },
                        {
                            "id": "200",
                            "type": 1,
                            "allow": str(int(fluxer.Permissions.SEND_MESSAGES)),
                            "deny": "0",
                        },
                    ],
                }
            ],
        },
        http,
    )


def test_permission_overwrite_tri_state_aliases_and_pair_conversion() -> None:
    overwrite = fluxer.PermissionOverwrite(
        send_messages=True,
        read_message_history=False,
        create_invite=True,
    )
    assert overwrite.send_messages is True
    assert overwrite.read_message_history is False
    assert overwrite.create_instant_invite is True
    assert overwrite.create_invite is True

    overwrite.send_messages = None
    overwrite.update(use_voice_activity_detection=False)
    assert overwrite.send_messages is None
    assert overwrite.use_vad is False
    assert dict(overwrite)["manage_channels"] is None

    allow, deny = overwrite.pair()
    assert allow == fluxer.Permissions.CREATE_INSTANT_INVITE
    assert deny == (
        fluxer.Permissions.READ_MESSAGE_HISTORY | fluxer.Permissions.USE_VAD
    )
    assert fluxer.PermissionOverwrite.from_pair(allow, deny) == overwrite
    assert fluxer.PermissionOverwrite().is_empty()
    assert not overwrite.is_empty()


def test_permission_overwrite_rejects_invalid_input_atomically() -> None:
    overwrite = fluxer.PermissionOverwrite(send_messages=True)
    with pytest.raises(ValueError, match="Unknown permission"):
        overwrite.update(view_channel=False, unknown_permission=True)
    assert overwrite.view_channel is None
    with pytest.raises(TypeError, match="bool or None"):
        fluxer.PermissionOverwrite(send_messages=1)  # type: ignore[arg-type]
    with pytest.raises(AttributeError):
        overwrite.unknown_permission = True


def test_channel_overwrite_wire_parsing_and_typed_records() -> None:
    maximum = (1 << 63) - 1
    channel = fluxer.Channel.from_data(
        {
            "id": "30",
            "guild_id": "10",
            "type": 0,
            "permission_overwrites": [
                {"id": "20", "type": 0, "allow": str(maximum), "deny": None},
                {"id": "200", "type": 1},
            ],
        }
    )
    assert channel.permission_overwrites == [
        {"id": "20", "type": 0, "allow": str(maximum), "deny": "0"},
        {"id": "200", "type": 1, "allow": "0", "deny": "0"},
    ]
    assert channel.overwrites[0] == fluxer.ChannelPermissionOverwrite(
        20,
        fluxer.PermissionOverwriteType.ROLE,
        fluxer.Permissions(maximum),
        fluxer.Permissions(0),
    )
    assert channel.overwrites[1].type is fluxer.PermissionOverwriteType.MEMBER
    with pytest.raises(TypeError, match="permission mask"):
        fluxer.Channel.from_data(
            {
                "id": "30",
                "guild_id": "10",
                "type": 0,
                "permission_overwrites": [
                    {"id": "20", "type": 0, "allow": False, "deny": "0"}
                ],
            }
        )


def test_effective_permissions_and_overwrite_inspection() -> None:
    guild = permission_guild()
    channel = guild.channels[0]
    owner, member, administrator = guild.members

    assert int(channel.permissions_for(owner)) == (1 << 64) - 1
    assert int(channel.permissions_for(administrator)) == (1 << 64) - 1
    effective = channel.permissions_for(member)
    assert effective & fluxer.Permissions.VIEW_CHANNEL
    assert effective & fluxer.Permissions.SEND_MESSAGES
    assert channel.overwrites_for(member).send_messages is True
    assert channel.overwrites_for(guild.roles[1]).send_messages is False
    assert channel.overwrites_for(
        999, type=fluxer.PermissionOverwriteType.MEMBER
    ).is_empty()
    assert channel.permissions_for(fluxer.User(id=999)) == fluxer.Permissions(0)


def test_effective_permissions_require_complete_guild_cache() -> None:
    guild = permission_guild()
    channel = guild.channels[0]
    guild.roles = [role for role in guild.roles if role.id != 20]
    with pytest.raises(RuntimeError, match="role snapshot is incomplete"):
        channel.permissions_for(guild.members[1])
    with pytest.raises(TypeError, match="only on guild channels"):
        fluxer.Channel(id=1, type=1).permissions_for(fluxer.User(id=2))
    with pytest.raises(RuntimeError, match="bound guild context"):
        fluxer.Channel(id=1, type=0, guild_id=10).permissions_for(fluxer.User(id=2))


@pytest.mark.asyncio
async def test_set_permissions_infers_targets_and_updates_local_state() -> None:
    http = PermissionHTTP()
    guild = permission_guild(http)
    channel = guild.channels[0]
    role = guild.roles[1]
    member = guild.members[1]

    await channel.set_permissions(role, overwrite=fluxer.PermissionOverwrite())
    assert http.edits[-1] == (30, 20, {"allow": 0, "deny": 0, "type": 0})
    assert channel.permission_overwrites[-1] == {
        "id": "20",
        "type": 0,
        "allow": "0",
        "deny": "0",
    }

    await channel.set_permissions(member.user, send_messages=False)
    assert http.edits[-1][1:] == (
        200,
        {
            "allow": 0,
            "deny": int(fluxer.Permissions.SEND_MESSAGES),
            "type": 1,
        },
    )
    assert channel.overwrites_for(member).send_messages is False

    await channel.set_permissions(member, overwrite=None)
    assert http.deletes[-1] == (30, 200)
    assert channel.overwrites_for(member).is_empty()


@pytest.mark.asyncio
async def test_set_permissions_rejects_invalid_targets_and_input_before_request() -> (
    None
):
    http = PermissionHTTP()
    guild = permission_guild(http)
    channel = guild.channels[0]
    with pytest.raises(TypeError, match="bare target ID"):
        await channel.set_permissions(20, send_messages=True)
    with pytest.raises(TypeError, match="either overwrite"):
        await channel.set_permissions(
            guild.roles[1],
            overwrite=fluxer.PermissionOverwrite(),
            send_messages=True,
        )
    with pytest.raises(TypeError, match="Provide an overwrite"):
        await channel.set_permissions(guild.roles[1])
    with pytest.raises(ValueError, match="conflicts"):
        await channel.set_permissions(
            guild.roles[1],
            type=fluxer.PermissionOverwriteType.MEMBER,
            send_messages=True,
        )
    with pytest.raises(ValueError, match="different guild"):
        await channel.set_permissions(
            fluxer.Role(id=50, name="Elsewhere", guild_id=99),
            send_messages=True,
        )
    with pytest.raises(ValueError, match="positive integer"):
        await channel.set_permissions(
            0,
            type=fluxer.PermissionOverwriteType.ROLE,
            send_messages=True,
        )
    assert http.edits == [] and http.deletes == []


@pytest.mark.asyncio
async def test_permission_http_routes_validate_and_declare_feature() -> None:
    http = HTTPClient("test", api_url="https://instance.test/v1")
    http.request = AsyncMock(return_value=None)
    await http.edit_channel_permissions(30, 20, allow=1 << 54, deny="0", type=0)
    assert http.request.call_args.args[0].method == "PUT"
    assert http.request.call_args.kwargs["json"] == {
        "type": 0,
        "allow": str(1 << 54),
        "deny": "0",
    }
    assert http.request.call_args.kwargs["headers"] == {
        "X-Fluxer-Features": "view_channel_members_permission"
    }
    await http.delete_channel_permissions(30, 20)
    assert http.request.call_args.args[0].method == "DELETE"
    assert http.request.call_args.kwargs["headers"] == {
        "X-Fluxer-Features": "view_channel_members_permission"
    }
    with pytest.raises(ValueError, match="Overwrite type"):
        await http.edit_channel_permissions(30, 20, type=2)
    with pytest.raises(ValueError, match="between"):
        await http.edit_channel_permissions(30, 20, allow=1 << 63)


@pytest.mark.asyncio
async def test_rest_and_gateway_updates_replace_overwrite_collection() -> None:
    client = fluxer.Client()
    http_client = HTTPClient("test", api_url="https://instance.test/v1")
    client._http = http_client
    client._state.http = http_client
    await client._dispatch(
        "GUILD_CREATE",
        {
            "id": "10",
            "owner_id": "100",
            "roles": [{"id": "10", "permissions": "0"}],
            "channels": [
                {
                    "id": "30",
                    "type": 0,
                    "permission_overwrites": [
                        {"id": "10", "type": 0, "allow": "1", "deny": "0"}
                    ],
                }
            ],
        },
    )
    http: Any = http_client
    http.get_channel = AsyncMock(
        return_value={
            "id": "30",
            "guild_id": "10",
            "type": 0,
            "permission_overwrites": [
                {"id": "20", "type": 0, "allow": "4", "deny": "0"}
            ],
        }
    )
    fetched = await client.fetch_channel("30")
    assert fetched.guild is client.get_guild(10)
    assert fetched.permission_overwrites == [
        {"id": "20", "type": 0, "allow": "4", "deny": "0"}
    ]
    await client._dispatch(
        "CHANNEL_UPDATE",
        {
            "id": "30",
            "guild_id": "10",
            "type": 0,
            "permission_overwrites": [
                {"id": "200", "type": 1, "allow": "0", "deny": "2"}
            ],
        },
    )
    channel = client.get_channel(30)
    assert channel is not None
    assert channel.permission_overwrites == [
        {"id": "200", "type": 1, "allow": "0", "deny": "2"}
    ]
    await client.close()
