from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BaseActivity:
    name: str | None = None
    type: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "type": self.type}
        for key, value in self._extra_payload().items():
            if value is not None:
                payload[key] = value
        return payload

    def _extra_payload(self) -> dict[str, Any]:
        return {}


class Activity(BaseActivity):
    pass


class Game(BaseActivity):
    def __init__(self, name: str) -> None:
        super().__init__(name=name, type=0)


class Streaming(BaseActivity):
    def __init__(self, *, name: str, url: str) -> None:
        super().__init__(name=name, type=1)
        self.url = url

    def _extra_payload(self) -> dict[str, Any]:
        return {"url": self.url}


class CustomActivity(BaseActivity):
    pass


class Spotify(BaseActivity):
    pass


def create_activity(data: dict[str, Any] | None) -> BaseActivity | None:
    if data is None:
        return None
    return Activity(name=data.get("name"), type=data.get("type", 0))
