/**
 * Frontend patient tests — Phase 3.
 *
 * Covers the five key test cases from the Phase 3 plan:
 *   1. PatientCombobox renders and searches — type text → results shown
 *   2. PatientCombobox create flow — zero results → "Create" option → opens modal
 *   3. PatientCreateModal submits — fill fields → createPatient called → onCreated fired
 *   4. PatientLinkModal links patient — select patient, confirm → patchJob called
 *   5. PatientLinkModal unlinks — click unlink (in confirmation dialog) → patchJob with null
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { PatientCombobox } from "@/components/patients/PatientCombobox";
import { PatientCreateModal } from "@/components/patients/PatientCreateModal";
import { PatientLinkModal } from "@/components/patients/PatientLinkModal";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// Mock the patients API so tests do not make real HTTP calls.
vi.mock("@/api/patients", () => ({
  searchPatients: vi.fn(),
  createPatient: vi.fn(),
  listPatients: vi.fn(),
  getPatientDetail: vi.fn(),
  updatePatient: vi.fn(),
  deletePatient: vi.fn(),
}));

// Mock patchJob from the jobs API for the link-modal tests.
vi.mock("@/api/jobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/jobs")>();
  return {
    ...actual,
    patchJob: vi.fn(),
  };
});

// Import mocked versions after vi.mock is hoisted.
const { searchPatients, createPatient } = await import("@/api/patients");
const { patchJob } = await import("@/api/jobs");

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/** Create a fresh QueryClient for each test so cache never bleeds. */
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

/** Render a component with all required providers. */
function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

/** A realistic patient summary fixture for search results. */
const PATIENT_FIXTURE = {
  id: "pat-1",
  full_name: "Nguyen Van A",
  phone: "0901234567",
  date_of_birth: null,
  scan_count: 3,
  last_visit: null,
};

// ---------------------------------------------------------------------------
// Reset all mocks before each test
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.resetAllMocks();
});

// ---------------------------------------------------------------------------
// Test 1 — PatientCombobox renders and searches
// ---------------------------------------------------------------------------

describe("PatientCombobox — search", () => {
  it("shows patient results after typing a search query", async () => {
    vi.mocked(searchPatients).mockResolvedValue([PATIENT_FIXTURE]);

    const user = userEvent.setup();
    const handleChange = vi.fn();

    renderWithProviders(
      <PatientCombobox value={null} onChange={handleChange} />,
    );

    // Open the popover by clicking the trigger combobox.
    const trigger = screen.getByRole("combobox", { name: /search patient/i });
    await user.click(trigger);

    // Type a search query — the debounce hook will fire with the query.
    const input = screen.getByPlaceholderText(/name or phone/i);
    await user.type(input, "Nguyen");

    // The hook debounces 300 ms; wait for the result to appear.
    await waitFor(() => {
      expect(screen.getByText("Nguyen Van A")).toBeInTheDocument();
    });

    // The phone number should also be visible.
    expect(screen.getByText("0901234567")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Test 2 — PatientCombobox create flow
// ---------------------------------------------------------------------------

describe("PatientCombobox — create flow", () => {
  it("shows a 'Create' option when search returns no results", async () => {
    vi.mocked(searchPatients).mockResolvedValue([]);

    const user = userEvent.setup();
    renderWithProviders(
      <PatientCombobox value={null} onChange={vi.fn()} />,
    );

    await user.click(screen.getByRole("combobox", { name: /search patient/i }));

    const input = screen.getByPlaceholderText(/name or phone/i);
    await user.type(input, "Unknown");

    // The "Create" option should appear when the list is empty.
    await waitFor(() => {
      expect(screen.getByText(/Create "Unknown"/i)).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Test 3 — PatientCreateModal submits
// ---------------------------------------------------------------------------

describe("PatientCreateModal — submit", () => {
  it("calls createPatient and fires onCreated after successful form submit", async () => {
    vi.mocked(createPatient).mockResolvedValue({
      id: "new-pat-1",
      full_name: "Tran Thi B",
      phone: null,
      date_of_birth: null,
      notes: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    const onCreated = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <PatientCreateModal
        open={true}
        onOpenChange={vi.fn()}
        onCreated={onCreated}
      />,
    );

    // Fill in the required full name field.
    const nameInput = screen.getByLabelText(/full name/i);
    await user.type(nameInput, "Tran Thi B");

    // Submit the form.
    await user.click(screen.getByRole("button", { name: /create/i }));

    // createPatient should have been called with the filled payload.
    await waitFor(() => {
      expect(createPatient).toHaveBeenCalledWith(
        expect.objectContaining({ full_name: "Tran Thi B" }),
      );
    });

    // onCreated should fire with the new patient's id and name.
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith("new-pat-1", "Tran Thi B");
    });
  });
});

// ---------------------------------------------------------------------------
// Test 4 — PatientLinkModal links patient
// ---------------------------------------------------------------------------

describe("PatientLinkModal — link patient", () => {
  it("calls patchJob with selected patient id on confirm", async () => {
    vi.mocked(searchPatients).mockResolvedValue([PATIENT_FIXTURE]);
    vi.mocked(patchJob).mockResolvedValue({} as never);

    const onLinked = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <PatientLinkModal
        open={true}
        onOpenChange={vi.fn()}
        jobId="job-123"
        currentPatientId={null}
        currentPatientName={null}
        onLinked={onLinked}
      />,
    );

    // Open the combobox inside the dialog and search.
    const comboboxTrigger = screen.getByRole("combobox", { name: /search patient/i });
    await user.click(comboboxTrigger);

    const searchInput = screen.getByPlaceholderText(/name or phone/i);
    await user.type(searchInput, "Nguyen");

    // Wait for and click the search result.
    await waitFor(() => {
      expect(screen.getByText("Nguyen Van A")).toBeInTheDocument();
    });
    await user.click(screen.getByText("Nguyen Van A"));

    // Click the confirm button to save the link.
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    // patchJob should be called with the selected patient id.
    await waitFor(() => {
      expect(patchJob).toHaveBeenCalledWith("job-123", { patient_id: "pat-1" });
    });

    // onLinked should be called after success.
    await waitFor(() => {
      expect(onLinked).toHaveBeenCalled();
    });
  });
});

// ---------------------------------------------------------------------------
// Test 5 — PatientLinkModal unlinks patient
// ---------------------------------------------------------------------------

describe("PatientLinkModal — unlink patient", () => {
  it("calls patchJob with null patient_id when user confirms unlink", async () => {
    vi.mocked(patchJob).mockResolvedValue({} as never);

    const onLinked = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <PatientLinkModal
        open={true}
        onOpenChange={vi.fn()}
        jobId="job-456"
        currentPatientId="pat-1"
        currentPatientName="Nguyen Van A"
        onLinked={onLinked}
      />,
    );

    // Click the "Unlink Patient" button to open the confirmation dialog.
    await user.click(screen.getByRole("button", { name: /unlink patient/i }));

    // Confirm the unlink in the nested AlertDialog.
    const dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: /unlink/i }));

    // patchJob should be called with null patient_id.
    await waitFor(() => {
      expect(patchJob).toHaveBeenCalledWith("job-456", { patient_id: null });
    });

    await waitFor(() => {
      expect(onLinked).toHaveBeenCalled();
    });
  });
});
