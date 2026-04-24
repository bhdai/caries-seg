/**
 * OverlayCanvas
 *
 * Renders a <canvas> element that composites:
 *   1. The original (display-copy) radiograph as the base layer.
 *   2. A red highlight (rgba(255, 60, 60, opacity/100)) for every pixel in
 *      the mask where the grayscale value > 127.
 *   3. Bounding boxes for tooth detections (two-stage only).
 *
 * The pixel-by-pixel approach (getImageData / putImageData) avoids browser
 * inconsistencies with globalCompositeOperation on grayscale images.
 *
 * The canvas is redrawn whenever `opacity` changes; images are reused from
 * the HTMLImageElement cache — no extra network requests.
 */
import { fileUrl } from "@/api/files";
import type { BBoxResponse } from "@/api/types";
import * as BBoxLayer from "@/components/BBoxLayer";
import { useEffect, useRef } from "react";

export interface OverlayCanvasProps {
  /** ID of the ImageResult record (used to build API URLs). */
  imageResultId: string;
  /** Mask overlay opacity, 0–100. */
  opacity: number;
  /** Bounding boxes to draw (two-stage only; pass null/undefined otherwise). */
  boundingBoxes?: BBoxResponse[] | null;
  /** Whether tooth detection boxes should be drawn. */
  showBoundingBoxes?: boolean;
  /** Natural dimensions of the original image (used for aspect-ratio CSS). */
  originalSize: { width: number; height: number };
}

/**
 * Load an image from a URL, resolving when the `load` event fires.
 * Returns the loaded HTMLImageElement.
 */
function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load image: ${src}`));
    img.src = src;
  });
}

function createWorkingCanvas(
  width: number,
  height: number,
): OffscreenCanvas | HTMLCanvasElement {
  if (typeof OffscreenCanvas !== "undefined") {
    return new OffscreenCanvas(width, height);
  }

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

export function OverlayCanvas({
  imageResultId,
  opacity,
  boundingBoxes,
  showBoundingBoxes = true,
  originalSize,
}: OverlayCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Cache the loaded HTMLImageElement objects across re-renders so that
  // opacity changes don't trigger additional network requests.
  const originalImgRef = useRef<HTMLImageElement | null>(null);
  const maskImgRef = useRef<HTMLImageElement | null>(null);
  const loadedForIdRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      const canvas = canvasRef.current;
      if (!canvas) return;

      // (Re-)load images if this is the first render for this imageResultId.
      if (loadedForIdRef.current !== imageResultId) {
        try {
          const [orig, mask] = await Promise.all([
            loadImage(fileUrl(imageResultId, "original")),
            loadImage(fileUrl(imageResultId, "mask")),
          ]);
          if (cancelled) return;
          originalImgRef.current = orig;
          maskImgRef.current = mask;
          loadedForIdRef.current = imageResultId;
        } catch {
          // If either image fails to load, leave the canvas blank.
          return;
        }
      }

      const origImg = originalImgRef.current;
      const maskImg = maskImgRef.current;
      if (!origImg || !maskImg) return;

      const W = origImg.naturalWidth;
      const H = origImg.naturalHeight;

      canvas.width = W;
      canvas.height = H;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // 1. Draw base radiograph.
      ctx.drawImage(origImg, 0, 0);

      // 2. Extract mask pixel data via a working canvas.
      const offscreen = createWorkingCanvas(W, H);
      const octx = offscreen.getContext("2d");
      if (!octx) return;
      octx.drawImage(maskImg, 0, 0, W, H);
      const maskData = octx.getImageData(0, 0, W, H);

      // 3. Build overlay image data: red highlight where mask > 127.
      const alpha = Math.round((opacity / 100) * 255);
      const overlayData = ctx.createImageData(W, H);
      for (let i = 0; i < maskData.data.length; i += 4) {
        if (maskData.data[i] > 127) {
          overlayData.data[i] = 255; // R
          overlayData.data[i + 1] = 60; // G
          overlayData.data[i + 2] = 60; // B
          overlayData.data[i + 3] = alpha; // A
        }
        // Transparent pixels (alpha = 0) are implicitly handled because
        // createImageData initialises all channels to 0.
      }
      // `putImageData` replaces the destination pixels, so compose the
      // overlay on a separate canvas and then draw that canvas on top.
      const overlayCanvas = createWorkingCanvas(W, H);
      const overlayCtx = overlayCanvas.getContext("2d");
      if (!overlayCtx) return;
      overlayCtx.putImageData(overlayData, 0, 0);
      ctx.drawImage(overlayCanvas, 0, 0);

      // 4. Draw bounding boxes on top, scaled from original-image pixels
      // into the display-copy canvas space.
      if (showBoundingBoxes) {
        const scaleX = originalSize.width > 0 ? W / originalSize.width : 1;
        const scaleY = originalSize.height > 0 ? H / originalSize.height : 1;
        BBoxLayer.draw(ctx, boundingBoxes, scaleX, scaleY);
      }
    }

    void render();

    return () => {
      cancelled = true;
    };
  }, [imageResultId, opacity, boundingBoxes, originalSize.height, originalSize.width, showBoundingBoxes]);

  // Calculate a CSS aspect-ratio so the canvas doesn't collapse before load.
  const aspectRatio =
    originalSize.width > 0 && originalSize.height > 0
      ? `${originalSize.width} / ${originalSize.height}`
      : "16 / 9";

  return (
    <canvas
      ref={canvasRef}
      className="w-full rounded-md border"
      style={{ aspectRatio }}
    />
  );
}
