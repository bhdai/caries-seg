// =============================================================================
// Files API
// =============================================================================
//
// URL helpers for accessing stored image files served by the backend.
// No network requests are made here; the returned strings are suitable for
// use as HTMLImageElement `src` attributes or anchor `href` values.

/**
 * Return the backend URL for a processed image file.
 *
 * @param imageResultId - The id of the ImageResult record.
 * @param kind - "original" for the input image, "mask" for the overlay.
 */
export function fileUrl(
  imageResultId: string,
  kind: "original" | "mask",
): string {
  return `/api/files/${imageResultId}/${kind}`;
}
