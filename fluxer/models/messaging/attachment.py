from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Attachment:
    """Represents a file attached to a Fluxer message."""

    id: int
    filename: str
    size: int
    url: str
    proxy_url: str | None = None
    width: int | None = None
    height: int | None = None
    content_type: str | None = None
    description: str | None = None
    ephemeral: bool = False

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> Attachment:
        return cls(
            id=int(data["id"]),
            filename=data["filename"],
            size=int(data["size"]),
            url=data["url"],
            proxy_url=data.get("proxy_url"),
            width=int(data["width"]) if data.get("width") is not None else None,
            height=int(data["height"]) if data.get("height") is not None else None,
            content_type=data.get("content_type"),
            description=data.get("description"),
            ephemeral=data.get("ephemeral", False),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the Attachment to a dictionary for API requests."""
        data: dict[str, Any] = {
            "id": str(self.id),
            "filename": self.filename,
            "size": self.size,
            "url": self.url,
            "ephemeral": self.ephemeral,
        }
        if self.proxy_url is not None:
            data["proxy_url"] = self.proxy_url
        if self.width is not None:
            data["width"] = self.width
        if self.height is not None:
            data["height"] = self.height
        if self.content_type is not None:
            data["content_type"] = self.content_type
        if self.description is not None:
            data["description"] = self.description

        return data
