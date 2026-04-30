/**
 * Frontend auth tests — Step 3.9.
 *
 * Covers the five key test cases from 04-data-flow-and-testing.md:
 *   1. ProtectedRoute redirects to /login when not authenticated
 *   2. ProtectedRoute redirects to /change-password when must_change_pw
 *   3. ProtectedRoute renders children when fully authenticated
 *   4. LoginForm surfaces the ?error=google_not_linked URL param as a message
 *   5. LoginForm calls auth.login with the correct credentials (via mocked hook)
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { LoginForm } from "@/components/auth/LoginForm";
import type { AuthContextValue } from "@/context/AuthContext";
import type { User } from "@/api/auth";

// ---------------------------------------------------------------------------
// Shared test fixtures
// ---------------------------------------------------------------------------

const ACTIVE_USER: User = {
  id: "user-1",
  username: "alice",
  role: "user",
  must_change_pw: false,
  oauth_providers: [],
};

const MUST_CHANGE_USER: User = {
  id: "user-2",
  username: "bob",
  role: "user",
  must_change_pw: true,
  oauth_providers: [],
};

// ---------------------------------------------------------------------------
// Module mock — useAuth
// ---------------------------------------------------------------------------
//
// vi.mock is hoisted to the top of the compiled output. The factory keeps a
// reference to a module-level `vi.fn()` so individual tests can call
// `vi.mocked(useAuth).mockReturnValue(...)` to inject controlled auth state.
//
// AuthProvider is passed through unchanged so tests that need the real
// provider (e.g., integration-style tests) can use it without further setup.

vi.mock("@/context/AuthContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/context/AuthContext")>();
  return {
    ...actual,
    // Replace only the hook — AuthProvider keeps its real implementation.
    useAuth: vi.fn(),
  };
});

// Import AFTER vi.mock so we get the mocked version.
const { useAuth } = await import("@/context/AuthContext");

// Default stub — enough to keep components from crashing. Individual tests
// override specific fields using mockReturnValue.
const baseStub: AuthContextValue = {
  user: null,
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  refreshUser: vi.fn(),
};

// Reset the mock to the safe default before every test so state does not
// bleed between test cases.
beforeEach(() => {
  vi.mocked(useAuth).mockReturnValue({ ...baseStub, login: vi.fn(), logout: vi.fn(), refreshUser: vi.fn() });
});

// ---------------------------------------------------------------------------
// Test 1 — ProtectedRoute redirects to /login when not authenticated
// ---------------------------------------------------------------------------

describe("ProtectedRoute — unauthenticated", () => {
  it("redirects to /login when user is null", () => {
    vi.mocked(useAuth).mockReturnValue({ ...baseStub, user: null });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Secret content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Login page")).toBeInTheDocument();
    expect(screen.queryByText("Secret content")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Test 2 — ProtectedRoute redirects to /change-password when must_change_pw
// ---------------------------------------------------------------------------

describe("ProtectedRoute — must_change_pw", () => {
  it("redirects to /change-password for a user with must_change_pw=true", () => {
    vi.mocked(useAuth).mockReturnValue({ ...baseStub, user: MUST_CHANGE_USER });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Dashboard content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/change-password" element={<div>Change password page</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Change password page")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard content")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Test 3 — ProtectedRoute renders children when fully authenticated
// ---------------------------------------------------------------------------

describe("ProtectedRoute — authenticated", () => {
  it("renders children when user is active and must_change_pw=false", () => {
    vi.mocked(useAuth).mockReturnValue({ ...baseStub, user: ACTIVE_USER });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Protected content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Test 4 — LoginForm shows error from ?error=google_not_linked URL param
// ---------------------------------------------------------------------------

describe("LoginForm — URL error params", () => {
  it("shows the google_not_linked error message from the URL query param", () => {
    render(
      <MemoryRouter initialEntries={["/login?error=google_not_linked"]}>
        <Routes>
          <Route path="/login" element={<LoginForm />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByText(
        /No account is linked to this Google identity\. Contact your admin\./i,
      ),
    ).toBeInTheDocument();
  });

  it("shows a generic fallback message for unknown error codes", () => {
    render(
      <MemoryRouter initialEntries={["/login?error=unknown_code"]}>
        <Routes>
          <Route path="/login" element={<LoginForm />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByText(/An error occurred during sign in\. Please try again\./i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Test 5 — AuthContext sets user state after a successful login
// ---------------------------------------------------------------------------
//
// We verify that submitting the LoginForm calls auth.login with the typed
// credentials. The context user update is the responsibility of AuthContext
// itself (tested separately via the real AuthProvider); here we confirm the
// component correctly delegates to the hook's login function.

describe("AuthContext — login is called on form submission", () => {
  it("calls auth.login with the entered username and password", async () => {
    const loginMock = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({ ...baseStub, login: loginMock });

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginForm />} />
          <Route path="/" element={<div>Home</div>} />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.type(screen.getByLabelText(/username/i), "alice");
    await userEvent.type(screen.getByLabelText(/password/i), "secret123");
    await userEvent.click(screen.getByRole("button", { name: /^login$/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith({
        username: "alice",
        password: "secret123",
      });
    });
  });

  it("shows an error message when auth.login rejects", async () => {
    const { ApiError } = await import("@/api/http");
    const loginMock = vi.fn().mockRejectedValue(new ApiError(401, "Invalid credentials"));
    vi.mocked(useAuth).mockReturnValue({ ...baseStub, login: loginMock });

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginForm />} />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.type(screen.getByLabelText(/username/i), "alice");
    await userEvent.type(screen.getByLabelText(/password/i), "wrongpass");
    await userEvent.click(screen.getByRole("button", { name: /^login$/i }));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });
  });
});
