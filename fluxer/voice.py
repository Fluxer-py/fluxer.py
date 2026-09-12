"""Optional LiveKit voice connections and FFmpeg PCM playback.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

# pyright: reportMissingImports=false

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
    """An audio source that reads from a file via ffmpeg.

    Note:
        Requires the `voice` extra: `pip install fluxer.py[voice]`.

    Attributes:
        path: Filesystem path or operation path accepted by this method.
        executable: FFmpeg executable name or path.
        before_options: FFmpeg options placed before the input argument.
        options: FFmpeg options appended after the input argument.
        sample_rate: PCM sample rate expected by the audio source.
        num_channels: Number of PCM channels used for playback.
    """

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
        """Initialize the ffmpeg pcmaudio with the supplied configuration.

        Args:
            path: Filesystem path or operation path accepted by this method.
            executable: FFmpeg executable name or path.
            before_options: FFmpeg options placed before the input argument.
            options: FFmpeg options appended after the input argument.
            sample_rate: PCM sample rate expected by the audio source.
            num_channels: Number of PCM channels used for playback.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        self.path: str = path
        self.executable: str = executable
        self.before_options: str | None = before_options
        self.options: str | None = options
        self.sample_rate: int = sample_rate
        self.num_channels: int = num_channels


class VoiceClient:
    """Manages a voice connection to a channel via LiveKit.

    Note:
        Requires the `voice` extra: `pip install fluxer.py[voice]`.

    Attributes:
        is_connected: Return whether the underlying connection is currently established.
        is_playing: Return whether this voice client has a published audio track.
        is_paused: Return whether playback is paused while an audio track is published.
        channel_id: Channel id.
        guild_id: Guild id.
    """

    def __init__(self, guild_id: int, channel_id: int, gateway: Gateway) -> None:
        """Initialize the voice client with the supplied configuration.

        Args:
            guild_id: Identity of the guild used by this operation.
            channel_id: Identity of the channel used by this operation.
            gateway: Gateway used by this operation.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._gateway = gateway
        self._connection_id: str | None = None
        self._failure: Exception | None = None
        self._placement = asyncio.Event()
        self._room: rtc.Room | None = None
        self._connected = asyncio.Event()
        self._current_track: rtc.LocalAudioTrack | None = None
        self._current_publication: rtc.LocalTrackPublication | None = None
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._playback_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        """Return whether the underlying connection is currently established.

        Returns:
            Whether the documented condition holds for the current state.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        return self._room is not None and self._connected.is_set()

    @property
    def is_playing(self) -> bool:
        """Return whether this voice client has a published audio track.

        Returns:
            Whether the documented condition holds for the current state.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        return self._current_publication is not None

    @property
    def is_paused(self) -> bool:
        """Return whether playback is paused while an audio track is published.

        Returns:
            Whether the documented condition holds for the current state.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        return self._current_publication is not None and not self._resume_event.is_set()

    @property
    def channel_id(self) -> int:
        """Channel id.

        Returns:
            The result of this operation.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        return self._channel_id

    @property
    def guild_id(self) -> int:
        """Guild id.

        Returns:
            The result of this operation.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        return self._guild_id

    def pause(self) -> None:
        """Pause reads feeding the current voice playback.

        Returns:
            None.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        self._resume_event.clear()

    def resume(self) -> None:
        """Resume reads feeding the current voice playback.

        Returns:
            None.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        self._resume_event.set()

    async def _wait_until_connected(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self._placement.wait(), timeout=timeout)
        if self._failure is not None:
            raise self._failure

    async def _on_voice_server_update(
        self,
        endpoint: str,
        token: str,
        connection_id: str,
    ) -> None:
        """Connect with the issued grant and remember its connection identity."""
        self._connection_id = connection_id
        self._connected.clear()
        if self._room is not None:
            await self.stop()
            await self._room.disconnect()
        room = rtc.Room()
        self._room = room

        def disconnected(*args: Any) -> None:
            if self._room is room:
                self._connected.clear()

        room.on("disconnected", disconnected)
        try:
            await room.connect(endpoint, token)
        except Exception as exc:
            self._failure = exc
            await room.disconnect()
            self._room = None
        else:
            self._connected.set()
        finally:
            self._placement.set()

    def _reject_placement(self, message: str) -> None:
        self._failure = RuntimeError(message)
        self._placement.set()

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
        """Publish an audio source through the active LiveKit connection.

        Args:
            source: Audio source published through the active LiveKit connection.
            after: Completion callback receiving the playback error, or None on success.

        Returns:
            None.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
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

        # Keep ffmpeg process handling predictable for background playback.
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
        """Stop.

        Returns:
            None.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
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
        """Convenience wrapper around play(FFmpegPCMAudio(...)) that blocks until done. Added for testing and simple playback.

        Args:
            path: Filesystem path or operation path accepted by this method.
            after: Completion callback receiving the playback error, or None on success.

        Returns:
            None.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        await self.play(
            FFmpegPCMAudio(path),
            after=after,
        )
        if self._playback_task is not None:
            await self._playback_task

    async def disconnect(self) -> None:
        """Leave the issued voice connection and release LiveKit resources.

        Requires the optional voice extra. Repeated calls are safe.

        Returns:
            None.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        await self.stop()
        try:
            if self._connection_id is not None and self._gateway.is_connected:
                await self._gateway.update_voice_state(
                    guild_id=str(self._guild_id),
                    channel_id=None,
                    connection_id=self._connection_id,
                )
        finally:
            if self._room is not None:
                await self._room.disconnect()
                self._room = None
            self._connected.clear()
            self._connection_id = None

    async def __aenter__(self) -> VoiceClient:
        """Enter the asynchronous context and return this object.

        Returns:
            This instance, allowing chained calls.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        return self

    async def __aexit__(self, *_: object) -> None:
        """Release resources when leaving the asynchronous context.

        Args:
            *_:  used by this operation.

        Returns:
            None.

        Note:
            Requires the `voice` extra: `pip install fluxer.py[voice]`.
        """
        await self.disconnect()


__all__ = ("FFmpegPCMAudio", "VoiceClient")
