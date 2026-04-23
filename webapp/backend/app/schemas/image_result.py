"""Pydantic schemas for ``ImageResult`` response payloads."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class BBoxResponse(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class ImageResultResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    original_size: dict[str, Any]
    inference_time_ms: int | None
    bounding_boxes: list[BBoxResponse] | None

    model_config = {"from_attributes": True}
