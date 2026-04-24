/**
 * BBoxLayer
 *
 * Not a React component — exports a single `draw` function that paints
 * tooth bounding boxes (with confidence labels) onto an existing 2D canvas
 * context.  Called by OverlayCanvas after the mask overlay is drawn.
 *
 * Colour: #00e5ff (cyan) — legible on dark dental radiographs.
 */
import type { BBoxResponse } from "@/api/types";

/**
 * Draw all bounding boxes onto `ctx`.
 *
 * @param ctx   - Canvas 2D rendering context already prepared with the base
 *                image and mask overlay.
 * @param boxes - Array of bounding-box records from the API.  Pass an empty
 *                array or undefined to skip drawing.
 */
export function draw(
  ctx: CanvasRenderingContext2D,
  boxes: BBoxResponse[] | null | undefined,
  scaleX: number,
  scaleY: number,
): void {
  if (!boxes || boxes.length === 0) return;

  ctx.save();
  ctx.strokeStyle = "#00e5ff";
  ctx.fillStyle = "#00e5ff";
  ctx.lineWidth = 2;
  ctx.font = "bold 13px sans-serif";

  for (const box of boxes) {
    const x1 = box.x1 * scaleX;
    const y1 = box.y1 * scaleY;
    const x2 = box.x2 * scaleX;
    const y2 = box.y2 * scaleY;
    const w = x2 - x1;
    const h = y2 - y1;
    const labelY = Math.max(14, y1 + 14);

    ctx.strokeRect(x1, y1, w, h);
    ctx.fillText(
      `Tooth ${box.confidence.toFixed(2)}`,
      x1 + 4,
      labelY,
    );
  }

  ctx.restore();
}
