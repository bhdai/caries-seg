// =============================================================================
// resultExport
// =============================================================================
//
// Browser-only helpers for exporting inference result images.
//
// Two export paths are provided:
//
//   1. `exportSingleResultPng` — download one overlay composite as a PNG file.
//      The filename is derived from the source image name so the user can
//      identify it in their downloads folder.
//
//   2. `exportReadyResultsZip` — export multiple overlay composites into a
//      single ZIP archive.  Images are processed sequentially to bound browser
//      memory usage.  Per-item failures are collected and returned in the
//      outcome object so the UI can report partial success without hiding the
//      successfully exported files.
//
// Both functions accept a callback that returns the PNG Blob rather than
// touching DOM refs directly.  This keeps the lib layer decoupled from the
// React component tree.

import JSZip from "jszip";

// =============================================================================
// Types
// =============================================================================

/**
 * Describe one image to include in a batch ZIP export.
 */
export interface BatchExportItem {
  /** The image result UUID — used to build a stable filename. */
  imageResultId: string;
  /** The original source filename — used as the base for the archive entry. */
  originalFilename: string;
  /**
   * Callback that produces the PNG Blob for this image.
   * Typically wraps `OverlayCanvasHandle.exportPngBlob()`.
   */
  exportCanvas: () => Promise<Blob>;
}

/**
 * Summary returned after a batch export attempt.
 *
 * The caller should check `failedItems` to decide whether to surface a
 * partial-success message rather than a plain success toast.
 */
export interface BatchExportOutcome {
  /** Number of images successfully written into the ZIP. */
  succeededCount: number;
  /** Original filenames that could not be exported. */
  failedItems: string[];
  /** The ZIP archive filename that was triggered for download. */
  archiveFilename: string;
}

// =============================================================================
// Internal helpers
// =============================================================================

/**
 * Sanitise a filename so it is safe as a ZIP archive entry name.
 * Strips path separators and replaces runs of whitespace with underscores.
 */
function sanitiseFilename(name: string): string {
  return name
    .replace(/[/\\]/g, "_")
    .replace(/\s+/g, "_");
}

/**
 * Derive a stable export filename for one result PNG.
 *
 * The original source filename's extension is replaced with `.png` so the
 * exported file is always a PNG regardless of the input format.
 */
function deriveExportFilename(originalFilename: string): string {
  const dotIndex = originalFilename.lastIndexOf(".");
  const stem =
    dotIndex > 0 ? originalFilename.slice(0, dotIndex) : originalFilename;
  return sanitiseFilename(`${stem}_overlay.png`);
}

/**
 * Trigger a browser file download from a Blob with the given filename.
 */
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    // The anchor must be in the document for Firefox compatibility.
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  } finally {
    // Revoke immediately; the browser has already queued the download.
    URL.revokeObjectURL(url);
  }
}

// =============================================================================
// Public API
// =============================================================================

/**
 * Export one overlay composite as a PNG file and trigger a browser download.
 *
 * @param originalFilename - The source image filename used to derive the
 *   download name.
 * @param exportCanvas - Async function that returns the PNG Blob for the
 *   current canvas state (opacity, bounding boxes, etc.).
 */
export async function exportSingleResultPng(
  originalFilename: string,
  exportCanvas: () => Promise<Blob>,
): Promise<void> {
  const blob = await exportCanvas();
  const filename = deriveExportFilename(originalFilename);
  triggerDownload(blob, filename);
}

/**
 * Export multiple ready image results as a single ZIP archive of PNG files.
 *
 * Images are processed sequentially to bound browser memory usage.
 * Per-item failures are collected and returned so the UI can report partial
 * success without hiding the successfully exported images.
 *
 * @param jobId - The parent job UUID, used to build the archive filename.
 * @param items - Array of image export descriptors in the desired archive
 *   entry order (typically server-result order).
 * @returns An outcome object with succeeded count, failed item names, and the
 *   triggered archive filename.
 */
export async function exportReadyResultsZip(
  jobId: string,
  items: BatchExportItem[],
): Promise<BatchExportOutcome> {
  const zip = new JSZip();
  const failedItems: string[] = [];
  let succeededCount = 0;

  // Sequentially write each canvas blob into the archive so only one large
  // Blob is held in memory at a time.
  for (const item of items) {
    try {
      const blob = await item.exportCanvas();
      const entryName = deriveExportFilename(item.originalFilename);
      zip.file(entryName, blob);
      succeededCount += 1;
    } catch {
      // Record the failure and continue so partial results are still saved.
      failedItems.push(item.originalFilename);
    }
  }

  // Build the archive filename from a short job-id prefix so the user can
  // correlate the download to a specific job.
  const shortId = jobId.slice(0, 8);
  const archiveFilename = `caries_results_${shortId}.zip`;

  if (succeededCount === 0) {
    // Nothing to download — surface this as an error instead of creating an
    // empty archive.
    throw new Error("No images could be exported.");
  }

  const archiveBlob = await zip.generateAsync({ type: "blob" });
  triggerDownload(archiveBlob, archiveFilename);

  return { succeededCount, failedItems, archiveFilename };
}
