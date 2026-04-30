// =============================================================================
// Admin API Layer
// =============================================================================
//
// Typed wrappers around the /api/admin/users endpoints. All calls require an
// authenticated admin session cookie — the backend enforces this via the
// require_admin dependency and will return 403 for non-admin users.

import { apiFetch, buildQueryString } from "@/api/http";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AdminUserResponse {
  id: string;
  username: string;
  role: "user" | "admin";
  must_change_pw: boolean;
  has_password: boolean;
  oauth_providers: string[];
  created_at: string;
}

export interface UserListResponse {
  items: AdminUserResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateUserPayload {
  username: string;
  password: string;
  role: "user" | "admin";
}

export interface UpdateUserPayload {
  role?: "user" | "admin" | null;
  new_password?: string | null;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Fetch a paginated list of all users.
 */
export async function listAdminUsers(
  page = 1,
  pageSize = 20,
): Promise<UserListResponse> {
  const qs = buildQueryString({ page, page_size: pageSize });
  const res = await apiFetch(`/api/admin/users${qs}`);
  return (await res.json()) as UserListResponse;
}

/**
 * Create a new user with a temporary password.
 * The backend sets must_change_pw=true automatically.
 */
export async function createAdminUser(
  payload: CreateUserPayload,
): Promise<AdminUserResponse> {
  const res = await apiFetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await res.json()) as AdminUserResponse;
}

/**
 * Update a user's role and/or reset their password.
 * Resetting the password also sets must_change_pw=true.
 */
export async function updateAdminUser(
  userId: string,
  payload: UpdateUserPayload,
): Promise<AdminUserResponse> {
  const res = await apiFetch(`/api/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await res.json()) as AdminUserResponse;
}

/**
 * Delete a user. Their jobs are orphaned (owner_id set to NULL) and become
 * visible to admins only — diagnostic data is never auto-deleted.
 */
export async function deleteAdminUser(userId: string): Promise<void> {
  await apiFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
}
