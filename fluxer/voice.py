from __future__ import annotations

import asyncio
import logging
import shlex
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .gateway import Gateway

log = logging.getLogger(__name__)

try:
    import livekit.rtc as rtc
except ImportError:
    raise ImportError(
        "Voice support requires the 'voice' extra: pip install fluxer.py[voice]"
    ) from None


class FFmpegPCMAudio:
    """An audio source that reads from a file via ffmpeg."""

    def __init__(
        self,
        path: str,
        *,
        executable: str = "ffmpeg",
        before_options: str | None = None,
        options: str | None = None,
        sample_rate: int = 48000,
        num_channels: int = 2,
    ) -> None:
        self.path = path
        self.executable = executable
        self.before_options = before_options
        self.options = options
        self.sample_rate = sample_rate
        self.num_channels = num_channels


class VoiceClient:
    """Manages a voice connection to a channel via LiveKit."""

    def __init__(self, guild_id: int, channel_id: int, gateway: Gateway) -> None:
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._gateway = gateway
        self._room: rtc.Room | None = None
        self._connected = asyncio.Event()
        self._current_track: rtc.LocalAudioTrack | None = None
        self._current_publication: rtc.LocalTrackPublication | None = None
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._playback_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._room is not None and self._connected.is_set()

    @property
    def is_playing(self) -> bool:
        return self._current_publication is not None

    @property
    def is_paused(self) -> bool:
        return self._current_publication is not None and not self._resume_event.is_set()

    @property
    def channel_id(self) -> int:
        return self._channel_id

    @property
    def guild_id(self) -> int:
        return self._guild_id

    def pause(self) -> None:
        self._resume_event.clear()

    def resume(self) -> None:
        self._resume_event.set()

    async def _wait_until_connected(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self._connected.wait(), timeout=timeout)

    async def _on_voice_server_update(
        self, endpoint: str, token: str, session_id: str
    ) -> None:
        """Called by Client when VOICE_SERVER_UPDATE happens for this guild."""
        self._room = rtc.Room()
        await self._room.connect(endpoint, token)

        self._connected.set()
        log.info(
            "voice connected: guild_id=%s channel_id=%s",
            self._guild_id,
            self._channel_id,
        )

    async def _publish_track(self, source: rtc.AudioSource) -> None:
        if self._room is None:
            raise RuntimeError("Cannot play audio before connecting to a voice channel")

        track = rtc.LocalAudioTrack.create_audio_track("audio", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)

        self._current_publication = await self._room.local_participant.publish_track(
            track, options
        )
        self._current_track = track

    async def play(
        self,
        source: FFmpegPCMAudio | rtc.AudioSource,
        *,
        after: Callable[[Exception | None], Any] | None = None,
    ) -> None:
        await self.stop()
        if isinstance(source, FFmpegPCMAudio):
            self._playback_task = asyncio.get_running_loop().create_task(
                self._run_ffmpeg(source, after)
            )
        else:
            if after is not None:
                raise TypeError("after= is not supported for a raw AudioSource")
            await self._publish_track(source)

    async def _run_ffmpeg(
        self,
        source: FFmpegPCMAudio,
        after: Callable[[Exception | None], Any] | None,
    ) -> None:
        error: Exception | None = None
        try:
            await self._run_ffmpeg_loop(source)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            error = e
            log.exception("ffmpeg playback error")
        finally:
            self._resume_event.set()
            if self._room is not None and self._current_publication is not None:
                try:
                    await self._room.local_participant.unpublish_track(
                        self._current_publication.sid
                    )
                except Exception:
                    pass
            self._current_track = None
            self._current_publication = None
            self._playback_task = None
            if after:
                try:
                    result = after(error)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    log.exception(f"exception in audio callback: {e}")

    async def _run_ffmpeg_loop(self, source: FFmpegPCMAudio) -> None:
        if self._room is None:
            raise RuntimeError("Cannot play audio before connecting to a voice channel")

        # 20ms Opus frames at 48kHz = 960 samples; s16le = 2 bytes/sample
        chunk_bytes = 960 * source.num_channels * 2

        # Keeping this close to discord.py's implementation
        args = [source.executable]
        if source.before_options:
            args += shlex.split(source.before_options)
        args += [
            "-i",
            source.path,
            "-vn",
            "-f",
            "s16le",
            "-ar",
            str(source.sample_rate),
            "-ac",
            str(source.num_channels),
            "-loglevel",
            "warning",
        ]
        if source.options:
            args += shlex.split(source.options)
        args.append("pipe:1")

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        if proc.stdout is None:
            raise RuntimeError("ffmpeg did not open stdout")

        rtc_source = rtc.AudioSource(source.sample_rate, source.num_channels)
        await self._publish_track(rtc_source)

        try:
            while True:
                await self._resume_event.wait()
                data = await proc.stdout.read(chunk_bytes)
                if not data:
                    break

                if len(data) < chunk_bytes:  # pad final chunk with silence
                    data = data + b"\x00" * (chunk_bytes - len(data))
                n_samples = len(data) // (2 * source.num_channels)
                frame = rtc.AudioFrame(
                    data=data,
                    sample_rate=source.sample_rate,
                    num_channels=source.num_channels,
                    samples_per_channel=n_samples,
                )
                await rtc_source.capture_frame(frame)
                await asyncio.sleep(n_samples / source.sample_rate)
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

    async def stop(self) -> None:
        if self._playback_task is not None and not self._playback_task.done():
            self._playback_task.cancel()
            try:
                await self._playback_task
            except (asyncio.CancelledError, Exception):
                pass
            return

        self._resume_event.set()
        if self._room is not None and self._current_publication is not None:
            await self._room.local_participant.unpublish_track(
                self._current_publication.sid
            )
        self._current_track = None
        self._current_publication = None

    async def play_file(
        self,
        path: str,
        *,
        after: Callable[[Exception | None], Any] | None = None,
    ) -> None:
        """Convenience wrapper around play(FFmpegPCMAudio(...)) that blocks until done. Added for testing and simple playback"""
        await self.play(
            FFmpegPCMAudio(path),
            after=after,
        )
        if self._playback_task is not None:
            await self._playback_task

    async def disconnect(self) -> None:
        await self.stop()
        await self._gateway.update_voice_state(
            guild_id=str(self._guild_id), channel_id=None
        )

        if self._room:
            await self._room.disconnect()
            self._room = None
        self._connected.clear()

    async def __aenter__(self) -> VoiceClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()
