"""Documented sub-objects parse into typed models instead of plain dicts."""

from typing import Any

import fluxer
from fluxer.audit_logs import AuditLog, AuditLogChange, AuditLogOptions
from fluxer.fluxer_models import UserConnection
from fluxer.invite import Invite, PartialGuild, PartialInviteChannel
from fluxer.models import (
    ChannelMention,
    Embed,
    EmbedAuthor,
    EmbedField,
    EmbedFooter,
    EmbedMedia,
    EmbedProvider,
    Message,
    MessageCall,
    PendingBulkMessageDeletion,
    User,
    UserProfile,
)
from fluxer.models.profile import GuildMemberProfile, MutualGuild
from fluxer.utils import process_embed_args

RECEIVED_EMBED: dict[str, Any] = {
    "type": "rich",
    "title": "Title",
    "color": 5,
    "author": {"name": "A", "icon_url": "i", "proxy_icon_url": "p"},
    "footer": {"text": "F"},
    "image": {"url": "u", "proxy_url": "pu", "width": 10, "height": 20},
    "provider": {"name": "Site", "url": "s"},
    "fields": [{"name": "n", "value": "v", "inline": True}],
    "children": [{"type": "link", "title": "child"}],
}


def test_received_embed_parts_are_typed_and_round_trip() -> None:
    embed = Embed.from_dict(RECEIVED_EMBED)
    assert isinstance(embed.author, EmbedAuthor) and embed.author.proxy_icon_url == "p"
    assert isinstance(embed.footer, EmbedFooter) and embed.footer.text == "F"
    assert isinstance(embed.image, EmbedMedia) and embed.image.width == 10
    assert isinstance(embed.provider, EmbedProvider) and embed.provider.name == "Site"
    assert embed.fields == [EmbedField(name="n", value="v", inline=True)]
    assert embed.children is not None and embed.children[0].title == "child"
    assert embed.to_dict() == RECEIVED_EMBED


def test_builder_and_request_payload_are_unchanged() -> None:
    embed = (
        Embed(title="t")
        .set_author(name="a", icon_url="i")
        .set_footer(text="f")
        .set_image(url="img")
        .add_field(name="n", value="v")
    )
    assert embed.to_dict() == {
        "title": "t",
        "footer": {"text": "f"},
        "image": {"url": "img"},
        "author": {"name": "a", "icon_url": "i"},
        "fields": [{"name": "n", "value": "v", "inline": False}],
    }
    received = Embed.from_dict(RECEIVED_EMBED)
    request = process_embed_args({"embed": received})["embeds"][0]
    assert request["author"] == {"name": "A", "icon_url": "i"}
    assert request["image"] == {"url": "u"}
    assert "provider" not in request and "children" not in request
    # Dicts given to the constructor are converted.
    assert isinstance(Embed(footer={"text": "x"}).footer, EmbedFooter)  # type: ignore[arg-type]


def test_message_embeds_call_and_channel_mentions() -> None:
    message = Message.from_data(
        {
            "id": "1",
            "channel_id": "2",
            "author": {"id": "3"},
            "content": "",
            "timestamp": "2026-01-01T00:00:00Z",
            "embeds": [RECEIVED_EMBED],
            "call": {"participants": ["3", "4"], "ended_timestamp": None},
            "mention_channels": [{"id": "5", "name": "general", "type": 0}],
        }
    )
    assert isinstance(message.embeds[0], Embed) and message.embeds[0].title == "Title"
    assert message.call == MessageCall(participants=[3, 4])
    assert message.mention_channels == [ChannelMention(id=5, name="general", type=0)]


def test_invite_nested_objects() -> None:
    invite = Invite.from_data(
        {
            "code": "abc",
            "type": 0,
            "guild": {"id": "1", "name": "g", "features": ["X"]},
            "channel": {
                "id": "2",
                "name": None,
                "type": 3,
                "recipients": [{"username": "u"}],
            },
            "inviter": {"id": "3", "username": "inv"},
        }
    )
    assert isinstance(invite.guild, PartialGuild) and invite.guild.features == ["X"]
    assert isinstance(invite.channel, PartialInviteChannel)
    assert [r.username for r in invite.channel.recipients] == ["u"]
    assert isinstance(invite.inviter, User) and invite.inviter.username == "inv"
    assert (invite.guild_id, invite.channel_id, invite.inviter_id) == (1, 2, 3)
    assert Invite.from_data({"code": "x"}).guild is None


def test_audit_log_nested_objects() -> None:
    log = AuditLog.from_data(
        {
            "audit_log_entries": [
                {
                    "id": "1",
                    "action_type": 22,
                    "user_id": "9",
                    "target_id": "8",
                    "options": {"delete_message_seconds": 60, "channel_id": "7"},
                    "changes": [{"key": "nick", "old_value": "a", "new_value": "b"}],
                }
            ],
            "users": [{"id": "9", "username": "mod"}],
            "webhooks": [{"id": "6", "type": 1, "name": "hook", "channel_id": "7"}],
        }
    )
    entry = log.entries[0]
    assert isinstance(entry.options, AuditLogOptions)
    assert entry.options.delete_message_seconds == 60 and entry.options.channel_id == 7
    assert entry.changes == [AuditLogChange(key="nick", old_value="a", new_value="b")]
    assert log.users[0].username == "mod"
    assert log.webhooks[0].name == "hook" and log.webhooks[0].channel_id == 7


def test_profile_and_user_nested_objects() -> None:
    profile = UserProfile.from_data(
        {
            "user": {"id": "1"},
            "user_profile": {},
            "guild_member_profile": {"bio": "b", "accent_color": 3},
            "mutual_guilds": [{"id": "2", "nick": "n"}],
            "connected_accounts": [
                {"id": "c", "type": "domain", "name": "x", "verified": True}
            ],
        }
    )
    assert profile.guild_member_profile == GuildMemberProfile(bio="b", accent_color=3)
    assert profile.mutual_guilds == [MutualGuild(id=2, nick="n")]
    assert isinstance(profile.connected_accounts[0], UserConnection)
    assert profile.connected_accounts[0].name == "x"

    user = User.from_data(
        {
            "id": "1",
            "pending_bulk_message_deletion": {
                "scheduled_at": "2026-01-01T00:00:00Z",
                "channel_count": 2,
                "message_count": 30,
            },
        }
    )
    assert user.pending_bulk_message_deletion == PendingBulkMessageDeletion(
        scheduled_at="2026-01-01T00:00:00Z", channel_count=2, message_count=30
    )


def test_top_level_exports() -> None:
    assert fluxer.EmbedField is EmbedField and fluxer.MessageCall is MessageCall


def test_unset_embed_parts_are_empty_not_none() -> None:
    embed = Embed(title="t")
    for part in (
        embed.author,
        embed.footer,
        embed.image,
        embed.thumbnail,
        embed.video,
        embed.audio,
        embed.provider,
    ):
        assert not part
    assert embed.author.name is None and embed.footer.text is None
    assert embed.image.url is None and embed.provider.name is None
    assert embed.to_dict() == {"title": "t"}

    embed.set_footer(text="f")
    assert embed.footer and embed.footer.text == "f"
    embed.footer = None  # type: ignore[assignment]
    assert isinstance(embed.footer, EmbedFooter) and not embed.footer
    embed.author = {"name": "a"}  # type: ignore[assignment]
    assert isinstance(embed.author, EmbedAuthor) and embed.author.name == "a"
    assert embed.to_dict() == {"title": "t", "author": {"name": "a"}}
    assert not Embed.from_dict({"type": "rich"}).thumbnail


def test_audit_log_change_distinguishes_absent_from_null() -> None:
    created = AuditLogChange.from_data({"key": "name", "new_value": "general"})
    cleared = AuditLogChange.from_data(
        {"key": "nick", "old_value": "a", "new_value": None}
    )
    assert not created.has_old_value and created.has_new_value
    assert created.old_value is None
    assert cleared.has_new_value and cleared.new_value is None
    diff = AuditLogChange.from_data(
        {"key": "permissions_diff", "new_value": {"added": ["8"], "removed": []}}
    )
    assert diff.new_value == {"added": ["8"], "removed": []}
