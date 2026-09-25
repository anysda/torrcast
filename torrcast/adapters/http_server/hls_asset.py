"""Имена, которые раздача HLS вправе выпускать наружу."""

from __future__ import annotations

import re
from typing import Final

HLS_ASSET: Final = re.compile(r"^(?:v\d+\.(?:ts|m4s)|init\.mp4|(?:index|stream)\.m3u8)$")

__all__ = ["HLS_ASSET"]
