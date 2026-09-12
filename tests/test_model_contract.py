"""Model regressions using documented HTTP and Gateway payload variants."""

import pytest

from fluxer import Client, Guild, Message, Permissions, Role, User
from fluxer.audit_logs import AuditLogEntry
from fluxer.fluxer_models import AppInfo, AuthSession, BulkEmojiResult, CallEligibility
from fluxer.models.message import DeletedReferencedMessage, MessageReference
from fluxer.models.reaction import PartialEmoji
from fluxer.permissions import _effective_permissions


def message(**extra):
    return {
        "id": "9",
        "channel_id": "2",
        "author": {"id": "3"},
        "timestamp": "2026-01-01T00:00:00Z",
        **extra,
    }


def test_partial_users_nested_guild_and_reference_variants():
    assert User.from_data({"id": "3"}).id == 3
    guild = Guild.from_data(
        {
            "id": "1",
            "properties": {"name": "Nested", "owner_id": "3"},
            "roles": [{"id": "1", "permissions": "8"}],
        }
    )
    assert guild.name == "Nested" and guild.roles[0].permissions == 8
    assert Message.from_data(message()).referenced_message is None
    deleted = Message.from_data(
        message(referenced_message=None, message_reference={"message_id": "8"})
    )
    assert isinstance(deleted.referenced_message, DeletedReferencedMessage)
    deleted._cache_guild(guild)
    assert deleted.referenced_message.id == 8
    assert MessageReference.from_data(
        {"message_id": "8", "attachment_ids": [], "embed_indices": []}
    ).to_dict() == {"message_id": "8", "attachment_ids": [], "embed_indices": []}


def test_expression_identity_role_ties_and_nonnumeric_audit_targets():
    assert str(PartialEmoji.from_data({"name": "👍"})) == "👍"
    assert PartialEmoji(id=1, name="before") == PartialEmoji(id=1, name="after")
    assert Role(10, "higher", position=1, guild_id=1) > Role(
        11, "lower", position=1, guild_id=1
    )
    assert (
        AuditLogEntry.from_data(
            {"id": "1", "action_type": 42, "target_id": "invite-code"}
        ).target_id
        == "invite-code"
    )


def test_payload_names_false_values_and_owner_identity():
    assert BulkEmojiResult.from_data(
        {"success": [{"id": "1"}], "failed": []}
    ).items == [{"id": "1"}]
    assert (
        AuthSession.from_data({"id_hash": "hashed", "masked_ip": "192.0.x.x"}).id
        == "hashed"
    )
    assert CallEligibility.from_data({"active": False, "silent": False}).active is False
    app = AppInfo.from_data(
        {
            "id": "1",
            "name": "app",
            "owner": {"id": "2"},
            "bot": {"id": "3"},
            "client_secret": "private",
        }
    )
    assert app.owner is not None and app.bot is not None
    assert app.owner.id == 2 and app.bot.id == 3
    assert "private" not in repr(app)


def test_permission_overwrite_precedence():
    send = int(Permissions.SEND_MESSAGES)
    guild = {"id": "1", "owner_id": "9"}
    member = {"roles": ["2", "3"]}
    roles = [{"id": "1", "permissions": str(send)}]
    overwrites = [
        {"id": "1", "type": 0, "deny": str(send)},
        {"id": "2", "type": 0, "allow": str(send)},
        {"id": "3", "type": 0, "deny": str(send)},
    ]
    assert (
        _effective_permissions(
            guild, member, roles, 4, {"permission_overwrites": overwrites}
        )
        & send
    )
    overwrites.append({"id": "4", "type": 1, "deny": str(send)})
    assert (
        not _effective_permissions(
            guild, member, roles, 4, {"permission_overwrites": overwrites}
        )
        & send
    )
    assert (
        _effective_permissions(
            guild, member, roles, 9, {"permission_overwrites": overwrites}
        )
        & send
    )
    assert int(Permissions.USE_EXTERNAL_STICKERS) == 1 << 37


@pytest.mark.asyncio
async def test_cache_deletions_and_changed_role_subset():
    client = Client()
    await client._dispatch(
        "GUILD_CREATE",
        {
            "id": "1",
            "properties": {"name": "guild"},
            "roles": [{"id": "1"}, {"id": "2"}],
            "channels": [{"id": "2", "type": 0}],
        },
    )
    await client._dispatch(
        "GUILD_ROLE_UPDATE_BULK",
        {"guild_id": "1", "roles": [{"id": "2", "name": "changed"}]},
    )
    assert len(client.guilds[0].roles) == 2
    await client._dispatch("MESSAGE_CREATE", message())
    cached = client._state.get_message(9)
    assert cached is not None and cached.guild_id == 1
    await client._dispatch("MESSAGE_DELETE", {"id": "9", "channel_id": "2"})
    assert client._state.get_message(9) is None
    await client._dispatch("GUILD_DELETE", {"id": "1", "unavailable": True})
    assert client.guilds[0].unavailable
    await client.close()


@pytest.mark.asyncio
async def test_guild_sync_replaces_collections_and_message_member_context():
    client = Client()
    await client._dispatch(
        "GUILD_CREATE",
        {
            "id": "1",
            "channels": [{"id": "2", "type": 0}],
            "members": [{"user": {"id": "3"}}],
        },
    )
    await client._dispatch("MESSAGE_CREATE", message(member={"nick": "author"}))
    cached = client._state.get_message(9)
    assert cached is not None and cached.member is not None
    assert cached.member.guild_id == 1
    assert client._state.members[(1, 3)].nick == "author"
    await client._dispatch(
        "GUILD_SYNC", {"id": "1", "channels": [], "members": [], "voice_states": []}
    )
    assert 2 not in client._channels
    assert (1, 3) not in client._state.members
    assert cached.channel is None
    assert cached.guild is client.guilds[0]
    await client.close()


@pytest.mark.asyncio
async def test_reaction_callback_observes_updated_cache():
    client = Client()
    await client._dispatch("MESSAGE_CREATE", message())
    observed = []

    @client.on("raw_reaction_add")
    async def observe(raw):
        cached = client._state.get_message(raw.message_id)
        assert cached is not None
        observed.append(cached.reactions[0].count)

    await client._dispatch(
        "MESSAGE_REACTION_ADD",
        {"message_id": "9", "channel_id": "2", "user_id": "3", "emoji": {"name": "x"}},
    )
    assert observed == [1]
    await client.close()


@pytest.mark.parametrize(
    "mode,extra",
    [
        ("singlepart", {"upload_url": "https://storage.test/signed"}),
        (
            "multipart",
            {
                "upload_id": "opaque",
                "part_size": 5,
                "parts": [
                    {"part_number": 1, "upload_url": "https://storage.test/part"}
                ],
            },
        ),
    ],
)
def test_upload_variant_serializes_documented_message_key(mode, extra):
    from fluxer.fluxer_models import AttachmentUpload

    upload = AttachmentUpload.from_data(
        {
            "id": 0,
            "filename": "a.bin",
            "file_size": 8,
            "content_type": "application/octet-stream",
            "upload_filename": "pending-key",
            "upload_mode": mode,
            **extra,
        }
    )
    assert upload.is_multipart == (mode == "multipart")
    assert upload.to_attachment_payload() == {
        "id": 0,
        "filename": "a.bin",
        "upload_filename": "pending-key",
    }


def test_settings_preserve_false_zero_and_empty_collections():
    from fluxer.fluxer_models import UserSettings

    settings = UserSettings.from_data(
        {
            "render_embeds": False,
            "afk_timeout": 0,
            "guild_folders": [],
            "restricted_guilds": ["12"],
        }
    )
    assert settings.render_embeds is False
    assert settings.afk_timeout == 0
    assert settings.guild_folders == []
    assert settings.restricted_guilds == [12]
