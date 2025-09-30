"""Utilities to serialise messages to/from the wire format."""
from __future__ import annotations

import json
from typing import Iterable, Iterator

from .messages import Message


class LineCodec:
    """Encode/decode newline separated JSON documents."""

    @staticmethod
    def encode(message: Message) -> bytes:
        return (json.dumps(message.to_dict(), separators=(",", ":")) + "\n").encode("utf-8")

    @staticmethod
    def decode(line: bytes) -> Message:
        raw = line.decode("utf-8").strip()
        if not raw:
            raise ValueError("empty line")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("expected JSON object")
        return Message.from_dict(data)


__all__ = ["LineCodec"]