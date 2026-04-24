"""Pydantic schemas for ``ImageResult`` response payloads."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, computed_field, model_validator


class BBoxResponse(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class ImageResultResponse(BaseModel):
    """Represent one image within a job-detail response.

    Expose only frontend-safe fields needed to render progress and results.
    ``is_ready`` means the final mask artifact exists and the image can be
    rendered as a completed result card.

    The raw ``mask_path`` column is intentionally excluded from the
    serialized output; only the derived boolean readiness contract is
    exposed so internal storage paths never leak to the browser.
    """

    id: uuid.UUID
    original_filename: str
    original_size: dict[str, Any]
    inference_time_ms: int | None
    bounding_boxes: list[BBoxResponse] | None
    # Readiness is derived from the ORM object during validation; it is
    # stored here after the model_validator runs so normal serialization
    # picks it up without needing a computed_field + property pattern.
    is_ready: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _derive_readiness(cls, data: Any) -> Any:
        """Compute ``is_ready`` from the ORM attribute ``mask_path``.

        When constructing from an ORM object (``from_attributes=True``),
        Pydantic passes the raw ORM instance as an object; when constructing
        from a dict (e.g. in tests), it passes a plain mapping.  Both paths
        are handled here so callers never have to supply ``is_ready``
        manually.
        """
        # ORM object path — access attributes directly.
        if hasattr(data, "mask_path"):
            mask_path = data.mask_path
            # Pydantic needs a mutable mapping to inject extra fields when
            # using from_attributes mode.  Convert the ORM object to a dict
            # of the fields we care about, then append is_ready.
            return {
                "id": data.id,
                "original_filename": data.original_filename,
                "original_size": data.original_size,
                "inference_time_ms": data.inference_time_ms,
                "bounding_boxes": data.bounding_boxes,
                "is_ready": mask_path is not None,
            }

        # Dict / mapping path — allow explicit override or derive from key.
        if isinstance(data, dict):
            if "is_ready" not in data:
                data = dict(data)
                data["is_ready"] = data.get("mask_path") is not None
        return data
