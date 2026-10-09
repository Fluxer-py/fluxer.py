"""Media Proxy assets exposed by models, and their download helpers."""

import io
from typing import Any
from unittest.mock import AsyncMock

import pytest

import fluxer
from fluxer import asset as asset_module
from fluxer.asset import Asset
from fluxer.http import HTTPClient
from fluxer.invite import PartialGuild
from fluxer.models import Attachment, Emoji, Guild, GuildMember, User, UserProfile
from fluxer.models.reaction import PartialEmoji

MEDIA = "https://media.example.test"
STATIC = "https://static.example.test"


def bound_http() -> HTTPClient:
    http = HTTPClient("test-token", api_url="https://api.example.test/v1")
    http._endpoints._values = {"media": MEDIA, "static_cdn": STATIC}
    return http


@pytest.fixture
def http() -> HTTPClient:
    return bound_http()


def test_user_assets(http: HTTPClient) -> None:
    user = User.from_data({"id": "42", "avatar": "a_anim", "banner": "ban"}, http)
    assert isinstance(user.avatar, Asset)
    assert user.avatar.url == f"{MEDIA}/avatars/42/a_anim.gif"
    assert user.avatar.is_animated() and user.avatar.key == "a_anim"
    assert user.avatar_url == user.avatar.url
    assert user.banner is not None
    assert user.banner_url == user.banner.url == f"{MEDIA}/banners/42/ban.png"
    assert user.display_avatar == user.avatar
    assert user.default_avatar.url == f"{STATIC}/avatars/0.png"

    plain = User.from_data({"id": "43"}, http)
    assert plain.avatar is None and plain.avatar_url is None and plain.banner is None
    assert plain.display_avatar == plain.default_avatar
    assert plain.display_avatar_url == f"{STATIC}/avatars/1.png"


def test_member_assets(http: HTTPClient) -> None:
    member = GuildMember.from_data(
        {"user": {"id": "42", "avatar": "acct"}, "avatar": "gav", "banner": "gban"},
        http,
        guild_id=99,
    )
    assert member.guild_avatar is not None and member.guild_banner is not None
    assert member.guild_avatar.url == f"{MEDIA}/guilds/99/users/42/avatars/gav.png"
    assert member.guild_banner_url == f"{MEDIA}/guilds/99/users/42/banners/gban.png"
    assert member.display_avatar == member.guild_avatar
    assert member.avatar == member.user.avatar
    assert member.default_avatar == member.user.default_avatar


def test_guild_and_partial_guild_assets(http: HTTPClient) -> None:
    payload = {
        "id": "7",
        "icon": "a_icon",
        "banner": "ban",
        "splash": "spl",
        "embed_splash": "emb",
    }
    for model in (
        Guild.from_data(payload, http),
        PartialGuild.from_data(payload, http),
    ):
        assert model.icon_hash == "a_icon"
        assert model.icon_url == f"{MEDIA}/icons/7/a_icon.gif"
        assert model.banner_url == f"{MEDIA}/banners/7/ban.png"
        assert model.splash_url == f"{MEDIA}/splashes/7/spl.png"
        assert model.embed_splash_url == f"{MEDIA}/embed-splashes/7/emb.png"
    bare = Guild.from_data({"id": "8"}, http)
    assert bare.icon is None and bare.banner_url is None


def test_profile_assets(http: HTTPClient) -> None:
    profile = UserProfile.from_data(
        {
            "user": {"id": "42"},
            "user_profile": {"banner": "pban"},
            "guild_member_profile": {"banner": "gpban"},
        },
        http,
        guild_id=99,
    )
    assert profile.banner_url == f"{MEDIA}/banners/42/pban.png"
    member_profile = profile.guild_member_profile
    assert member_profile is not None and member_profile.banner_hash == "gpban"
    assert member_profile.banner_url == f"{MEDIA}/guilds/99/users/42/banners/gpban.png"


def test_emoji_sticker_and_reaction_emoji_assets(http: HTTPClient) -> None:
    emoji = Emoji.from_data({"id": "5", "name": "e"}, http)
    assert emoji.url == f"{MEDIA}/emojis/5.webp"
    animated = Emoji.from_data({"id": "6", "name": "e", "animated": True}, http)
    assert animated.url == f"{MEDIA}/emojis/6.webp?animated=true"
    sticker = fluxer.Sticker.from_data({"id": "9", "name": "s"}, http)
    assert sticker.url == f"{MEDIA}/stickers/9.webp"

    custom = PartialEmoji.from_data({"id": "5", "name": "e"}, http)
    assert custom.asset == emoji.asset and custom.url == emoji.url
    unicode = PartialEmoji.from_data({"name": "🔥"}, http)
    assert unicode.asset is None and unicode.url is None


def test_transforms(http: HTTPClient) -> None:
    avatar = User.from_data({"id": "42", "avatar": "abc"}, http).avatar
    assert avatar is not None
    assert avatar.with_size(256).url == f"{MEDIA}/avatars/42/abc.png?size=256"
    assert avatar.with_size(64).with_size(512).url.endswith("?size=512")
    assert avatar.with_format("webp").url == f"{MEDIA}/avatars/42/abc.webp"
    assert avatar.with_static_format("jpg").url.endswith("abc.jpg")
    assert avatar.replace(size=128, format="webp").url.endswith("abc.webp?size=128")

    animated = Asset._from_avatar(http, 42, "a_x")
    assert animated.with_static_format("png") is animated
    assert animated.with_format("webp").url.endswith("a_x.webp")

    default = User.from_data({"id": "42"}, http).default_avatar
    assert default.with_size(512) is default and default.with_format("webp") is default

    for bad_size in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            avatar.with_size(bad_size)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        avatar.with_format("bmp")
    with pytest.raises(ValueError):
        avatar.with_static_format("gif")


def test_equality_hash_and_str(http: HTTPClient) -> None:
    first = Asset._from_avatar(http, 42, "abc")
    second = Asset._from_avatar(bound_http(), 42, "abc")
    assert first == second and hash(first) == hash(second)
    assert first != first.with_size(64)
    assert len({first, second, first.with_size(64)}) == 2
    assert str(first) == first.url


def test_unbound_asset_url_raises() -> None:
    avatar = User.from_data({"id": "1", "avatar": "abc"}).avatar
    assert avatar is not None
    with pytest.raises(RuntimeError):
        _ = avatar.url


@pytest.mark.asyncio
async def test_read_save_and_to_file(
    http: HTTPClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    download = AsyncMock(return_value=b"image")
    monkeypatch.setattr(asset_module, "_download", download)
    avatar = Asset._from_avatar(http, 42, "abc")

    assert await avatar.read() == b"image"
    download.assert_awaited_with(f"{MEDIA}/avatars/42/abc.png")

    buffer = io.BytesIO()
    assert await avatar.save(buffer) == 5
    assert buffer.tell() == 0 and buffer.read() == b"image"
    kept = io.BytesIO()
    await avatar.save(kept, seek_begin=False)
    assert kept.tell() == 5

    file = await avatar.to_file(spoiler=True)
    assert isinstance(file, fluxer.File)
    assert file.filename == "SPOILER_abc.png"

    emoji = Emoji.from_data({"id": "5", "name": "e"}, http)
    assert await emoji.read() == b"image"
    with pytest.raises(ValueError):
        await PartialEmoji.from_data({"name": "x"}, http).read()


@pytest.mark.asyncio
async def test_attachment_downloads_issued_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    async def fake_download(url: str) -> bytes:
        calls.append(url)
        return b"data"

    monkeypatch.setattr("fluxer.models.attachment._download", fake_download)
    attachment = Attachment.from_data(
        {
            "id": "1",
            "filename": "report.txt",
            "size": 4,
            "url": "https://media.example.test/attachments/1/report.txt?ex=1",
            "proxy_url": "https://proxy.example.test/report.txt",
            "description": "notes",
        }
    )
    assert await attachment.read() == b"data"
    assert await attachment.read(use_cached=True) == b"data"
    assert calls == [attachment.url, attachment.proxy_url]
    file = await attachment.to_file()
    assert file.filename == "report.txt" and file.description == "notes"


@pytest.mark.asyncio
async def test_guild_update_refreshes_renamed_image_fields() -> None:
    client = fluxer.Client()
    await client._dispatch("GUILD_CREATE", {"id": "1", "properties": {"icon": "old"}})
    guild = client.get_guild(1)
    assert guild is not None and guild.icon_hash == "old"
    await client._dispatch("GUILD_UPDATE", {"id": "1", "icon": "new", "banner": "b"})
    assert guild.icon_hash == "new" and guild.banner_hash == "b"
    await client._dispatch("GUILD_UPDATE", {"id": "1", "name": "renamed"})
    assert guild.icon_hash == "new"
    await client.close()


def test_top_level_export() -> None:
    assert fluxer.Asset is Asset
