"""Repeatable upload bytes and filenames with explicit file ownership.

This module documents the existing implementation and its supported public surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO


class File:
    """Represents a file to be uploaded to Fluxer.

    This class makes it easy to send files through Fluxer message routes.

    Args:
        fp: A file-like object, path string, or bytes to upload.
        filename: The filename to use when uploading. If not provided, will be
                 inferred from the file path or set to "untitled".
        spoiler: Whether to mark the file as a spoiler (adds SPOILER_ prefix).
        description: Optional description for the file (alt text).

    Examples:
        # From file path
        file = File("image.png")
        await channel.send(file=file)

        # From file path with custom filename
        file = File("data.json", filename="config.json")
        await channel.send(file=file)

        # From bytes
        data = b"Hello, world!"
        file = File(BytesIO(data), filename="hello.txt")
        await channel.send(file=file)

        # From open file handle
        with open("image.png", "rb") as f:
            file = File(f, filename="image.png")
            await channel.send(file=file)



    Attributes:
        fp: A file-like object, path string, or bytes to upload.
        spoiler: Whether to mark the file as a spoiler (adds SPOILER_ prefix).
        description: Optional description for the file (alt text).
        filename: The filename to use when uploading.
    """

    def __init__(
        self,
        fp: str | bytes | Path | BinaryIO,
        *,
        filename: str | None = None,
        spoiler: bool = False,
        description: str | None = None,
    ) -> None:
        """Initialize the file with the supplied configuration.

        Args:
            fp: Source file, path, or bytes used by the file operation.
            filename: Filename presented to the server and recipients.
            spoiler: Whether the upload filename receives the SPOILER_ prefix.
            description: Descriptive text associated with this object.
        """
        self.fp: str | bytes | Path | BinaryIO = fp
        self._filename = filename
        self.spoiler: bool = spoiler
        self.description: str | None = description
        self._data: bytes | None = None
        self._closer: BinaryIO | None = None
        self._original_pos: int | None = None

    @property
    def filename(self) -> str:
        """The filename to use when uploading.

        Returns:
            The result of this operation.
        """
        if self._filename:
            name = self._filename
        elif isinstance(self.fp, (str, Path)):
            name = Path(self.fp).name
        else:
            name = "untitled"

        # Add SPOILER_ prefix if spoiler is True
        if self.spoiler and not name.startswith("SPOILER_"):
            name = f"SPOILER_{name}"

        return name

    def _get_bytes(self) -> bytes:
        """Get the file content as bytes.

        Returns:
            The file content as bytes.
        """
        # Handle path string or Path object
        if isinstance(self.fp, (str, Path)):
            with open(self.fp, "rb") as f:
                return f.read()

        # Handle bytes directly
        elif isinstance(self.fp, bytes):
            return self.fp

        # Handle file-like object (BytesIO, file handle, etc.)
        else:
            # Save current position if seekable
            if hasattr(self.fp, "seek") and hasattr(self.fp, "tell"):
                try:
                    self._original_pos = self.fp.tell()
                    self.fp.seek(0)
                except (OSError, IOError):
                    # Not seekable, continue anyway
                    pass

            data = self.fp.read()

            # Restore position if we saved it
            if self._original_pos is not None:
                try:
                    self.fp.seek(self._original_pos)
                except (OSError, IOError):
                    pass

            return data

    def to_dict(self) -> dict[str, Any]:
        """Convert the File to the dictionary format expected by HTTPClient.

        Returns:
            A dictionary with 'data' and 'filename' keys.
        """
        if self._data is None:
            self._data = self._get_bytes()
        payload: dict[str, Any] = {"data": self._data, "filename": self.filename}
        if self.description is not None:
            payload["description"] = self.description
        return payload

    def close(self) -> None:
        """Close the underlying file handle if it was opened by this File object.

        Returns:
            None.
        """
        if self._closer:
            self._closer.close()

    def __enter__(self) -> File:
        """Enter the synchronous context and return this object.

        Returns:
            This instance, allowing chained calls.
        """
        return self

    def __exit__(self, *args: Any) -> None:
        """Release resources when leaving the synchronous context.

        Args:
            *args: Positional arguments forwarded to the wrapped callback.

        Returns:
            None.
        """
        self.close()

    def __repr__(self) -> str:
        """Return a diagnostic representation of this object.

        Returns:
            The result of this operation.
        """
        return f"<File filename={self.filename!r}>"


__all__ = ("File",)
