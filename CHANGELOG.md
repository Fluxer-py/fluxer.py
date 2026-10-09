# Changelog

## [0.5.0-alpha.5] (development) - 2026-10-09

### Added

- Added `Client.latency` (and `Bot.latency`), the gateway heartbeat round-trip time in seconds
- `GuildMember` can now be used wherever a `User` is expected: account attributes (`username`, `bot`, `avatar_url`, ...) and `send()`/`create_dm()` delegate to `member.user`
- Added `Context.fetch_author()`, which returns the author's `GuildMember` from the cache or over HTTP
- Added documented fields that models were missing: `Role.unicode_emoji`, `Sticker.nsfw`, `Message.channel_type`/`nicks`/`mention_here` (Message Create), `Guild.joined_at`/`unavailable_hidden`, `RawReactionActionEvent.member`, `WebAuthnCredential.rp_id` and `MFAState.backup_codes`
- Added `Guild.voice_states`
- Added `Asset`, the Fluxer Media Proxy image type, with `url`, `key`, `is_animated()`, `with_size()`, `with_format()`, `with_static_format()`, `replace()`, `read()`, `save()` and `to_file()`
- Added Asset properties: `User.avatar`/`default_avatar`/`display_avatar`/`banner`; `GuildMember.avatar`/`default_avatar`/`banner`/`guild_avatar`/`guild_banner`; `Guild` and `PartialGuild` `icon`/`banner`/`splash`/`embed_splash`; `UserProfile.banner`; `GuildMemberProfile.banner`; `Emoji.asset`, `Sticker.asset` and `PartialEmoji.asset`
- Added URL shortcuts: `User.display_avatar_url`, `GuildMember.display_avatar_url`/`guild_banner_url`, `Guild`/`PartialGuild` `banner_url`/`splash_url`/`embed_splash_url`, `GuildMemberProfile.banner_url`, and `url` on `Emoji`, `Sticker` and `PartialEmoji`
- Added `read()`, `save()` and `to_file()` to `Emoji`, `Sticker`, `PartialEmoji` and `Attachment`. Attachments download the URL Fluxer issued, or `proxy_url` with `use_cached=True`

### Changed

- Changed and commented some imports
- The first gateway heartbeat is now sent immediately after Hello instead of after a random delay, so `latency` is available right away

### Breaking

- `GuildMember.display_avatar` is now an `Asset` instead of a URL string. Use `display_avatar.url` or the new `display_avatar_url`
- Image hash fields were renamed to `*_hash` so the plain names can return an `Asset`: `Guild` and `PartialGuild` `icon`/`banner`/`splash`/`embed_splash` → `icon_hash`/`banner_hash`/`splash_hash`/`embed_splash_hash`; `UserProfile.banner` and `GuildMemberProfile.banner` → `banner_hash`; `Webhook.avatar` → `avatar_hash`; `Channel.icon` → `icon_hash`. The `avatar=`/`icon=` parameters of edit and create methods are unchanged
- In guilds, `Message.author`, `ctx.author`, and the user passed to `on_reaction_add` are now the author's `GuildMember` when the payload includes it or the member is cached, and a `User` otherwise. Code checking `isinstance(author, User)` must also accept `GuildMember`
- `Message.member` is now also set when the member comes from the cache, not only from the payload
- `GuildMember` equality and hashing now use the account ID, as `User` does, and a member equals the `User` with the same ID. Members were previously compared field by field and could not be hashed
- Renamed the guild-specific `GuildMember` fields: `avatar_hash` → `guild_avatar_hash`, `banner` → `guild_banner_hash`, `accent_color` → `guild_accent_color`, `mention_flags` → `guild_mention_flags`. The old names now return the account values from `member.user`
- Documented sub-objects are now typed models instead of dicts. Use attribute access (`embed.author.name`, `embed.fields[0].value`) instead of `["key"]`:
  - `Message.embeds`, `MessageSnapshot.embeds` and `WebhookMessage.embeds` are `list[Embed]`. `Embed.author`/`footer`/`image`/`thumbnail`/`video`/`audio`/`provider`/`fields`/`children` are `EmbedAuthor`/`EmbedFooter`/`EmbedMedia`/`EmbedProvider`/`EmbedField`/`Embed`. The `Embed` builder and the payloads it sends are unchanged, and dicts passed to `Embed(...)` are still accepted. A part the embed does not have is an empty, falsy object whose attributes are `None` (`embed.footer.text` is `None`, never an `AttributeError`), so test presence with `if embed.footer:` rather than `is None`
  - `Message.call` is a `MessageCall`, and `mention_channels` is a `list[ChannelMention]`
  - `Invite.guild`, `Invite.channel` and `Invite.inviter` are `PartialGuild`, `PartialInviteChannel` and `User`
  - `AuditLogEntry.options` and `changes` are `AuditLogOptions` and `list[AuditLogChange]` (ID fields as `int`). `AuditLog.users` and `webhooks` are `list[User]` and `list[AuditLogWebhook]`. `AuditLogDiff`/`AuditLogChanges` now alias these types. `AuditLogChange` values stay untyped (passed through as sent), and `has_old_value`/`has_new_value` tell an absent side apart from an explicit `null`
  - `UserProfile.guild_member_profile`, `mutual_guilds` and `connected_accounts` are `GuildMemberProfile`, `list[MutualGuild]` and `list[UserConnection]`
  - `User.pending_bulk_message_deletion` is a `PendingBulkMessageDeletion`

## [0.5.0-alpha.4] (development) - 2026-09-22

### Added

- Added `on_<gateway_event_name>_data` which listens to any gateway event and returns a raw data dict.
- Added `on_reaction_add`
- Added `Member.display_name` and `Member.display_avatar`
- Added `Sticker` as a core import
- Added `message.reference.resolved` to `Message` and `WebhookMessage`
- Added typed wrappers that expose Fluxer’s documented bits for raw model flag integers
- Parse forwarded-message snapshots into `list[MessageSnapshot]` on both `Message` and `WebhookMessage`

### Fixed

- Fixed `AttributeError: 'GuildMember' object has no attribute 'id'`

### Changed

- Improved caching for multiple objects.

### Documentation

- Added new entry
- Updated general lib info.

## [0.5.0-alpha.3] (development) - 2026-09-18

### Added

- Added rework version disclaimer to documentation
- Channel permission handling (read & write)
- Added default help command for fluxer.Bot

### Changed

- Moved documentation-like texts from README.md to the [docs site](https://py.fluxer.how)
- Removed legacy Bot implementation and moved to the new full-featured version

## [0.5.0-alpha.2] (development) - 2026-09-12

### Added, Changed & Fixed

A lot of things, again :)

This update changes basically every file to ensure that all of them follow Python >3.10 practices, code formatting and docstring formatting for future documentation. It also synchronizes the entire codebase to the current (2026-09-11) [Fluxer API documentation](https://docs.fluxer.app) to ensure that we use the right ratelimits and practices.

## [0.5.0-alpha.1] (development) - 2026-09-07

### Added

- New API usage: message search

## [0.5.0] (development) - 2026-09-02

### Added, Changed & Fixed

Initial rework
- Added, changed and fixed a LOT of things.

## [0.4.2] - 2026-03-30

### Added
- Added `escape_mentions` utility method (#73)
- Added subclassed bot example (#72)
- Added basic bot example (#71)
- Added setup hook (#67)
- Added `from_dict` method to Embeds class (#65)
- Added issue templates (#63)
- Added `Client.get_guild` method (#59)
- Added contribution guidelines (#58, #61)
- Added `ban_duration_seconds` parameter to `Guild.ban` (#60)
- Added support for triggering typing indicator in channels (#54)
- Added support for custom prefix handlers for Bot (#53)
- Added message pin and unpin functionality (#46)
- Added support for referenced messages in Message Model (#42)

### Changed
- Standardized embed handling for `message.send` and `channel.send` (#64)
- Improved guild caching and added reply caching (#47)

### Fixed
- Fixed closed sockets being silently dropped (#68)
- Fixed name representation for unicode emojis (#57)
- Fixed commands sorting for cogs (#57)
- Applied checks to development branch
- Fixed ruff format issues

### Documentation
- Improvements for repository contributions (#61)
- Added contributing guidelines (#51, #58)