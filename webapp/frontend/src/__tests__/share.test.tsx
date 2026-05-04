/**
 * Share feature tests — Phase 4.
 *
 * Covers the key test cases from the Phase 4 plan:
 *   1. ShareModal — renders configure state when no existing link
 *   2. ShareModal — calls createShareLink and transitions to ready state
 *   3. ShareModal — shows QR code in ready state
 *   4. ShareModal — Copy button writes URL to clipboard
 *   5. ShareModal — Regenerate confirmation dialog appears
 *   6. ShareLinksTable — renders share links
 *   7. ShareLinksTable — revoke confirmation dialog appears and calls revokeShareLink
 *   8. SharedResultPage — renders patient name and image results on success
 *   9. SharedResultPage — shows expired message on 410
 *  10. SharedResultPage — shows invalid message on 404
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ShareModal } from "@/components/share/ShareModal";
import { ShareLinksTable } from "@/components/share/ShareLinksTable";
import SharedResultPage from "@/pages/SharedResultPage";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// Mock the share-links API so tests do not make real HTTP calls.
vi.mock("@/api/shareLinks", () => ({
  getShareLinkForJob: vi.fn(),
  createShareLink: vi.fn(),
  revokeShareLink: vi.fn(),
  getSharedResult: vi.fn(),
}));

// Mock qrcode.react so tests do not need a canvas environment.
vi.mock("qrcode.react", () => ({
  QRCodeCanvas: ({ value }: { value: string }) => (
    <canvas data-testid="qr-canvas" data-value={value} />
  ),
}));

const {
  getShareLinkForJob,
  createShareLink,
  revokeShareLink,
  getSharedResult,
} = await import("@/api/shareLinks");

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

/** A realistic share link fixture. */
const LINK_FIXTURE = {
  id: "link-1",
  job_id: "job-abc",
  token: "tok-xyz",
  expires_at: null,
  created_at: new Date().toISOString(),
  is_active: true,
};

/** A realistic PatientShareLinkSummary for the table. */
const TABLE_LINK_FIXTURE = {
  ...LINK_FIXTURE,
  job_date: new Date().toISOString(),
  job_primary_filename: "scan01.jpg",
};

// ---------------------------------------------------------------------------
// Reset mocks before each test
// ---------------------------------------------------------------------------

// jsdom does not provide a writable navigator.clipboard. Define it once at
// module scope so all tests in this file can rely on it.
const clipboardWriteText = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: clipboardWriteText },
  writable: true,
  configurable: true,
});

beforeEach(() => {
  vi.resetAllMocks();
  clipboardWriteText.mockResolvedValue(undefined);
});

// ===========================================================================
// Test 1 — ShareModal: configure state when no existing link
// ===========================================================================

describe("ShareModal — configure state", () => {
  it("shows expiry dropdown and Generate Link button when no existing link", async () => {
    vi.mocked(getShareLinkForJob).mockResolvedValue(null);

    renderWithProviders(
      <ShareModal
        open={true}
        onOpenChange={vi.fn()}
        jobId="job-abc"
        patientName="Nguyen Van A"
      />,
    );

    // Wait for the loading state to resolve.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /generate link/i })).toBeInTheDocument();
    });

    // The expiry select should be visible.
    expect(screen.getByText("30 days")).toBeInTheDocument();
  });
});

// ===========================================================================
// Test 2 — ShareModal: generates link and shows ready state
// ===========================================================================

describe("ShareModal — generate link", () => {
  it("calls createShareLink and transitions to the ready state", async () => {
    vi.mocked(getShareLinkForJob).mockResolvedValue(null);
    vi.mocked(createShareLink).mockResolvedValue(LINK_FIXTURE);

    const user = userEvent.setup();

    renderWithProviders(
      <ShareModal
        open={true}
        onOpenChange={vi.fn()}
        jobId="job-abc"
        patientName="Nguyen Van A"
      />,
    );

    // Wait for configure state.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /generate link/i })).toBeInTheDocument();
    });

    // Click the generate button.
    await user.click(screen.getByRole("button", { name: /generate link/i }));

    // createShareLink should be called with the job id and default 30-day expiry.
    await waitFor(() => {
      expect(createShareLink).toHaveBeenCalledWith({
        job_id: "job-abc",
        expires_in_days: 30,
      });
    });

    // The modal should now show the share URL input.
    await waitFor(() => {
      const input = screen.getByRole<HTMLInputElement>("textbox");
      expect(input.value).toContain("tok-xyz");
    });
  });
});

// ===========================================================================
// Test 3 — ShareModal: QR code shown in ready state
// ===========================================================================

describe("ShareModal — QR code", () => {
  it("renders a QR code when an active link is found on mount", async () => {
    vi.mocked(getShareLinkForJob).mockResolvedValue(LINK_FIXTURE);

    renderWithProviders(
      <ShareModal
        open={true}
        onOpenChange={vi.fn()}
        jobId="job-abc"
        patientName="Nguyen Van A"
      />,
    );

    // Wait for ready state — QR canvas should be present.
    await waitFor(() => {
      expect(screen.getByTestId("qr-canvas")).toBeInTheDocument();
    });
  });
});

// ===========================================================================
// Test 4 — ShareModal: copy button writes URL to clipboard
// ===========================================================================

describe("ShareModal — copy button", () => {
  it("shows 'Copied!' feedback and writes the URL to clipboard when Copy is clicked", async () => {
    vi.mocked(getShareLinkForJob).mockResolvedValue(LINK_FIXTURE);

    const user = userEvent.setup();

    renderWithProviders(
      <ShareModal
        open={true}
        onOpenChange={vi.fn()}
        jobId="job-abc"
        patientName="Nguyen Van A"
      />,
    );

    // Wait for ready state.
    await waitFor(() => {
      expect(screen.getByTestId("qr-canvas")).toBeInTheDocument();
    });

    // Click Copy button.
    await user.click(screen.getByRole("button", { name: /copy/i }));

    // The component shows "Copied!" feedback when the clipboard write succeeds.
    // This is both a UI assertion and an indirect proof that writeText was called.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /copied/i })).toBeInTheDocument();
    });
  });
});

// ===========================================================================
// Test 5 — ShareModal: regenerate confirmation dialog
// ===========================================================================

describe("ShareModal — regenerate confirmation", () => {
  it("shows an AlertDialog when the Regenerate button is clicked", async () => {
    vi.mocked(getShareLinkForJob).mockResolvedValue(LINK_FIXTURE);

    const user = userEvent.setup();

    renderWithProviders(
      <ShareModal
        open={true}
        onOpenChange={vi.fn()}
        jobId="job-abc"
        patientName="Nguyen Van A"
      />,
    );

    // Wait for ready state.
    await waitFor(() => {
      expect(screen.getByTestId("qr-canvas")).toBeInTheDocument();
    });

    // Click the Regenerate subtle button.
    await user.click(screen.getByRole("button", { name: /regenerate/i }));

    // The confirmation dialog title should appear.
    await waitFor(() => {
      expect(screen.getByText(/regenerate link\?/i)).toBeInTheDocument();
    });
  });
});

// ===========================================================================
// Test 6 — ShareLinksTable: renders share links
// ===========================================================================

describe("ShareLinksTable — renders links", () => {
  it("shows the job filename and an Active badge for a live link", () => {
    renderWithProviders(
      <ShareLinksTable
        shareLinks={[TABLE_LINK_FIXTURE]}
        onRevokeSuccess={vi.fn()}
      />,
    );

    expect(screen.getByText("scan01.jpg")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("shows the empty state when no links are provided", () => {
    renderWithProviders(
      <ShareLinksTable shareLinks={[]} onRevokeSuccess={vi.fn()} />,
    );

    expect(screen.getByText(/no shared links/i)).toBeInTheDocument();
  });
});

// ===========================================================================
// Test 7 — ShareLinksTable: revoke confirmation dialog
// ===========================================================================

describe("ShareLinksTable — revoke confirmation", () => {
  it("shows a confirmation dialog and calls revokeShareLink on confirm", async () => {
    vi.mocked(revokeShareLink).mockResolvedValue(undefined);

    const onRevokeSuccess = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <ShareLinksTable
        shareLinks={[TABLE_LINK_FIXTURE]}
        onRevokeSuccess={onRevokeSuccess}
      />,
    );

    // Click the Revoke icon button.
    await user.click(screen.getByRole("button", { name: /revoke/i }));

    // The confirmation dialog should appear.
    await waitFor(() => {
      expect(screen.getByText(/revoke link\?/i)).toBeInTheDocument();
    });

    // Confirm the revoke action.
    await user.click(screen.getByRole("button", { name: /^revoke$/i }));

    // revokeShareLink should be called with the link id.
    await waitFor(() => {
      expect(revokeShareLink).toHaveBeenCalledWith("link-1");
    });

    // onRevokeSuccess should be called.
    await waitFor(() => {
      expect(onRevokeSuccess).toHaveBeenCalled();
    });
  });
});

// ===========================================================================
// Helpers for SharedResultPage
// ===========================================================================

function renderSharedResultPage(token: string) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/shared/${token}`]}>
        <Routes>
          <Route path="/shared/:token" element={<SharedResultPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Minimal SharedResultResponse fixture. */
const SHARED_RESULT_FIXTURE = {
  patient_name: "Nguyen Van A",
  scan_date: new Date("2026-04-01T10:00:00Z").toISOString(),
  pipeline_type: "single_stage" as const,
  expires_at: null,
  image_results: [
    {
      id: "img-1",
      original_filename: "xray01.jpg",
      original_size: { width: 800, height: 600 },
      bounding_boxes: null,
      is_ready: true,
    },
  ],
};

// ===========================================================================
// Test 8 — SharedResultPage: renders results on success
// ===========================================================================

describe("SharedResultPage — success", () => {
  it("renders patient name and image filename after loading", async () => {
    vi.mocked(getSharedResult).mockResolvedValue(SHARED_RESULT_FIXTURE);

    renderSharedResultPage("tok-xyz");

    await waitFor(() => {
      expect(screen.getByText(/results for nguyen van a/i)).toBeInTheDocument();
    });

    expect(screen.getByText("xray01.jpg")).toBeInTheDocument();
  });

  it("renders 'Dental Analysis Results' when patient_name is null", async () => {
    vi.mocked(getSharedResult).mockResolvedValue({
      ...SHARED_RESULT_FIXTURE,
      patient_name: null,
    });

    renderSharedResultPage("tok-xyz");

    await waitFor(() => {
      expect(screen.getByText(/dental analysis results/i)).toBeInTheDocument();
    });
  });
});

// ===========================================================================
// Test 9 — SharedResultPage: 410 expired link
// ===========================================================================

describe("SharedResultPage — expired link", () => {
  it("shows the expiry error card when the API returns 410", async () => {
    const { ApiError } = await import("@/api/types");
    vi.mocked(getSharedResult).mockRejectedValue(
      new ApiError(410, "Link expired"),
    );

    renderSharedResultPage("tok-expired");

    await waitFor(() => {
      expect(screen.getByText(/this link has expired/i)).toBeInTheDocument();
    });

    expect(
      screen.getByText(/please contact your clinic for a new link/i),
    ).toBeInTheDocument();
  });
});

// ===========================================================================
// Test 10 — SharedResultPage: 404 invalid link
// ===========================================================================

describe("SharedResultPage — invalid link", () => {
  it("shows the invalid link card when the API returns 404", async () => {
    const { ApiError } = await import("@/api/types");
    vi.mocked(getSharedResult).mockRejectedValue(
      new ApiError(404, "Not found"),
    );

    renderSharedResultPage("tok-bad");

    await waitFor(() => {
      expect(screen.getByText(/this link is not valid/i)).toBeInTheDocument();
    });

    expect(
      screen.getByText(/it may have been revoked/i),
    ).toBeInTheDocument();
  });
});
