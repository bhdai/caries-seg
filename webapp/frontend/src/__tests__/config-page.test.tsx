/**
 * Phase 0 contract tests — ConfigPage model-arch options.
 *
 * These tests guard the removal of the stale `attention_unet` frontend type
 * branch.  ConfigPage must only offer the two architectures that the backend
 * actually supports: UNet and Double-UNet.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

import ConfigPage from "@/pages/ConfigPage";
import { UploadStoreProvider, useUploadStore } from "@/context/UploadStore";
import { useEffect, type ReactNode } from "react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Seed the UploadStore with a minimal fake file so that ConfigPage does not
 * immediately redirect back to the upload route.
 */
function StoreSeeder({ children }: { children: ReactNode }) {
  const { setFiles } = useUploadStore();

  useEffect(() => {
    const fakeFile = new File(["x"], "xray.png", { type: "image/png" });
    setFiles([fakeFile]);
  }, [setFiles]);

  return <>{children}</>;
}

function renderConfigPage() {
  return render(
    <UploadStoreProvider>
      <MemoryRouter>
        <StoreSeeder>
          <ConfigPage />
        </StoreSeeder>
      </MemoryRouter>
    </UploadStoreProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ConfigPage — model architecture contract", () => {
  it("offers 'UNet' as a model architecture option", async () => {
    renderConfigPage();

    // The select trigger should show the default choice; verify the label
    // exists somewhere in the rendered output.
    expect(screen.getByText("UNet")).toBeInTheDocument();
  });

  it("offers 'Double-UNet' as a model architecture option", async () => {
    const user = userEvent.setup();
    renderConfigPage();

    // Open the architecture select to reveal all options.
    const trigger = screen.getByRole("combobox", { name: /architecture/i });
    await user.click(trigger);

    expect(screen.getByRole("option", { name: "Double-UNet" })).toBeInTheDocument();
  });

  it("does not offer 'AttentionUNet' as a model architecture option", async () => {
    const user = userEvent.setup();
    renderConfigPage();

    // Open the architecture select; AttentionUNet must be absent.
    const trigger = screen.getByRole("combobox", { name: /architecture/i });
    await user.click(trigger);

    expect(
      screen.queryByRole("option", { name: /attentionunet/i }),
    ).not.toBeInTheDocument();
  });

  it("does not pass 'attention_unet' to createJob when Run Inference is clicked", async () => {
    // Spy on the global fetch to confirm the submitted form never contains
    // attention_unet as the model_arch value.
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "00000000-0000-0000-0000-000000000001",
          status: "pending",
          pipeline_type: "single_stage",
          model_arch: "unet",
          error_message: null,
          created_at: new Date().toISOString(),
          image_results: [],
        }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      ),
    );

    const user = userEvent.setup();
    renderConfigPage();

    await user.click(screen.getByRole("button", { name: /run inference/i }));

    // Verify at least one POST /api/jobs call was made.
    const calls = fetchSpy.mock.calls;
    const jobCall = calls.find(
      ([url, init]) =>
        typeof url === "string" &&
        url.includes("/api/jobs") &&
        (init as RequestInit)?.method === "POST",
    );

    expect(jobCall).toBeDefined();

    // The submitted form data must not contain attention_unet.
    const body = (jobCall![1] as RequestInit).body as FormData;
    expect(body.get("model_arch")).not.toBe("attention_unet");

    fetchSpy.mockRestore();
  });
});
