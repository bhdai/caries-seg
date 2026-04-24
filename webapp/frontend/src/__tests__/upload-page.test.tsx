/**
 * Phase 0 contract tests — UploadPage upload-size limit.
 *
 * These tests guard the alignment between the frontend validation/copy and
 * the backend's real 10 MB per-file limit.  Any accidental revert of the
 * constant or UI text back to 20 MB will be caught here.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";

import UploadPage from "@/pages/UploadPage";
import { UploadStoreProvider } from "@/context/UploadStore";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderUploadPage() {
  return render(
    <UploadStoreProvider>
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    </UploadStoreProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UploadPage — upload size contract", () => {
  it("shows '10 MB' as the per-file size limit in the drop-zone copy", () => {
    renderUploadPage();

    // The drop-zone caption must state the real backend limit, not the
    // stale 20 MB value that was present before Phase 0 cleanup.
    expect(screen.getByText(/max 10 MB each/i)).toBeInTheDocument();
  });

  it("does not mention '20 MB' anywhere in the page copy", () => {
    renderUploadPage();

    // Guard against the old copy accidentally reappearing.
    expect(screen.queryByText(/20 MB/i)).not.toBeInTheDocument();
  });
});
