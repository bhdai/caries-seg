// =============================================================================
// Admin Users Page
// =============================================================================
//
// Management console for user accounts. Accessible only to admins — any
// non-admin who navigates here directly is redirected to "/".
//
// Layout:
//   - Page header with title and "Create User" toggle button
//   - Collapsible create form (Card) above the table
//   - Table showing all users with role badges, status indicators, and actions
//   - Per-row actions: reset password, toggle role, delete (with confirmation)
//
// Mutations are optimistic-free: each action awaits the API call and then
// refetches the full list so the table always reflects server state.

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  listAdminUsers,
  createAdminUser,
  updateAdminUser,
  deleteAdminUser,
  type AdminUserResponse,
} from "@/api/admin";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/api/http";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// ---------------------------------------------------------------------------
// Create-user form state
// ---------------------------------------------------------------------------

interface CreateFormState {
  username: string;
  password: string;
  role: "user" | "admin";
  error: string | null;
  isSubmitting: boolean;
}

const EMPTY_CREATE_FORM: CreateFormState = {
  username: "",
  password: "",
  role: "user",
  error: null,
  isSubmitting: false,
};

// ---------------------------------------------------------------------------
// Reset-password inline state
// ---------------------------------------------------------------------------

interface ResetPasswordState {
  userId: string;
  newPassword: string;
  error: string | null;
  isSubmitting: boolean;
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const navigate = useNavigate();

  const [users, setUsers] = useState<AdminUserResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);

  // Create-user form visibility
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createForm, setCreateForm] = useState<CreateFormState>(EMPTY_CREATE_FORM);

  // Delete confirmation dialog state
  const [deleteTarget, setDeleteTarget] = useState<AdminUserResponse | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Inline reset-password form state
  const [resetPasswordState, setResetPasswordState] =
    useState<ResetPasswordState | null>(null);

  // Non-admin redirect — backend enforces this too, but we avoid a
  // "flicker then 403" UX by redirecting immediately on the client side.
  useEffect(() => {
    if (currentUser !== null && currentUser.role !== "admin") {
      navigate("/", { replace: true });
    }
  }, [currentUser, navigate]);

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const loadUsers = useCallback(async () => {
    setIsLoading(true);
    setPageError(null);
    try {
      const result = await listAdminUsers();
      setUsers(result.items);
      setTotal(result.total);
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "Failed to load users.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  // ---------------------------------------------------------------------------
  // Create user
  // ---------------------------------------------------------------------------

  async function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (createForm.password.length < 8) {
      setCreateForm((f) => ({ ...f, error: "Password must be at least 8 characters." }));
      return;
    }
    setCreateForm((f) => ({ ...f, isSubmitting: true, error: null }));
    try {
      await createAdminUser({
        username: createForm.username,
        password: createForm.password,
        role: createForm.role,
      });
      setCreateForm(EMPTY_CREATE_FORM);
      setShowCreateForm(false);
      await loadUsers();
    } catch (err) {
      setCreateForm((f) => ({
        ...f,
        isSubmitting: false,
        error: err instanceof ApiError ? err.message : "Failed to create user.",
      }));
    }
  }

  // ---------------------------------------------------------------------------
  // Toggle role
  // ---------------------------------------------------------------------------

  async function handleToggleRole(user: AdminUserResponse) {
    const newRole = user.role === "admin" ? "user" : "admin";
    try {
      await updateAdminUser(user.id, { role: newRole });
      await loadUsers();
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "Failed to update role.");
    }
  }

  // ---------------------------------------------------------------------------
  // Reset password
  // ---------------------------------------------------------------------------

  async function handleResetPassword(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!resetPasswordState) return;
    if (resetPasswordState.newPassword.length < 8) {
      setResetPasswordState((s) =>
        s ? { ...s, error: "Password must be at least 8 characters." } : s,
      );
      return;
    }
    setResetPasswordState((s) => (s ? { ...s, isSubmitting: true, error: null } : s));
    try {
      await updateAdminUser(resetPasswordState.userId, {
        new_password: resetPasswordState.newPassword,
      });
      setResetPasswordState(null);
      await loadUsers();
    } catch (err) {
      setResetPasswordState((s) =>
        s
          ? {
              ...s,
              isSubmitting: false,
              error: err instanceof ApiError ? err.message : "Failed to reset password.",
            }
          : s,
      );
    }
  }

  // ---------------------------------------------------------------------------
  // Delete user
  // ---------------------------------------------------------------------------

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await deleteAdminUser(deleteTarget.id);
      setDeleteTarget(null);
      await loadUsers();
    } catch (err) {
      setPageError(err instanceof ApiError ? err.message : "Failed to delete user.");
      setDeleteTarget(null);
    } finally {
      setIsDeleting(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">User Management</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {total} user{total !== 1 ? "s" : ""} total
          </p>
        </div>
        <Button onClick={() => setShowCreateForm((v) => !v)}>
          {showCreateForm ? "Cancel" : "Create User"}
        </Button>
      </div>

      {/* Page-level error banner */}
      {pageError !== null && (
        <Alert variant="destructive">
          <AlertDescription>{pageError}</AlertDescription>
        </Alert>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Create user form                                                    */}
      {/* ------------------------------------------------------------------ */}
      {showCreateForm && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">New User</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} noValidate>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="grid gap-1.5">
                  <Label htmlFor="new-username">Username</Label>
                  <Input
                    id="new-username"
                    type="text"
                    autoComplete="off"
                    required
                    value={createForm.username}
                    onChange={(e) =>
                      setCreateForm((f) => ({ ...f, username: e.target.value }))
                    }
                    disabled={createForm.isSubmitting}
                  />
                </div>

                <div className="grid gap-1.5">
                  <Label htmlFor="new-password">Temporary Password</Label>
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    value={createForm.password}
                    onChange={(e) =>
                      setCreateForm((f) => ({ ...f, password: e.target.value }))
                    }
                    disabled={createForm.isSubmitting}
                  />
                </div>

                <div className="grid gap-1.5">
                  <Label htmlFor="new-role">Role</Label>
                  <Select
                    value={createForm.role}
                    onValueChange={(v) =>
                      setCreateForm((f) => ({
                        ...f,
                        role: v as "user" | "admin",
                      }))
                    }
                    disabled={createForm.isSubmitting}
                  >
                    <SelectTrigger id="new-role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="user">user</SelectItem>
                      <SelectItem value="admin">admin</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {createForm.error !== null && (
                <Alert variant="destructive" className="mt-4">
                  <AlertDescription>{createForm.error}</AlertDescription>
                </Alert>
              )}

              <div className="mt-4 flex justify-end">
                <Button type="submit" disabled={createForm.isSubmitting}>
                  {createForm.isSubmitting ? "Creating…" : "Create"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Users table                                                         */}
      {/* ------------------------------------------------------------------ */}
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Auth</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>

          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  Loading…
                </TableCell>
              </TableRow>
            )}

            {!isLoading && users.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  No users found.
                </TableCell>
              </TableRow>
            )}

            {users.map((u) => (
              <>
                <TableRow key={u.id}>
                  <TableCell className="font-medium">{u.username}</TableCell>

                  <TableCell>
                    <Badge variant={u.role === "admin" ? "default" : "secondary"}>
                      {u.role}
                    </Badge>
                  </TableCell>

                  <TableCell>
                    {u.must_change_pw ? (
                      <Badge variant="outline" className="text-amber-600 border-amber-300">
                        must change pw
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground text-xs">active</span>
                    )}
                  </TableCell>

                  <TableCell>
                    <div className="flex gap-1 flex-wrap">
                      {u.has_password && (
                        <Badge variant="outline" className="text-xs">password</Badge>
                      )}
                      {u.oauth_providers.map((p) => (
                        <Badge key={p} variant="outline" className="text-xs">{p}</Badge>
                      ))}
                    </div>
                  </TableCell>

                  <TableCell className="text-muted-foreground text-xs">
                    {new Date(u.created_at).toLocaleDateString()}
                  </TableCell>

                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      {/* Toggle role — prevent admin self-demotion */}
                      {u.id !== currentUser?.id && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void handleToggleRole(u)}
                        >
                          Make {u.role === "admin" ? "user" : "admin"}
                        </Button>
                      )}

                      {/* Expand inline reset-password form */}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          setResetPasswordState((s) =>
                            s?.userId === u.id
                              ? null
                              : { userId: u.id, newPassword: "", error: null, isSubmitting: false },
                          )
                        }
                      >
                        Reset pw
                      </Button>

                      {/* Delete — blocked for the currently logged-in admin */}
                      {u.id !== currentUser?.id && (
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => setDeleteTarget(u)}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>

                {/* Inline reset-password form row */}
                {resetPasswordState?.userId === u.id && (
                  <TableRow key={`${u.id}-reset`}>
                    <TableCell colSpan={6} className="bg-muted/30">
                      <form
                        onSubmit={handleResetPassword}
                        noValidate
                        className="flex items-end gap-3 py-1"
                      >
                        <div className="grid gap-1.5 min-w-[200px]">
                          <Label htmlFor={`reset-pw-${u.id}`}>New password</Label>
                          <Input
                            id={`reset-pw-${u.id}`}
                            type="password"
                            autoComplete="new-password"
                            required
                            minLength={8}
                            value={resetPasswordState.newPassword}
                            onChange={(e) =>
                              setResetPasswordState((s) =>
                                s ? { ...s, newPassword: e.target.value } : s,
                              )
                            }
                            disabled={resetPasswordState.isSubmitting}
                          />
                        </div>
                        {resetPasswordState.error !== null && (
                          <p className="text-sm text-destructive">
                            {resetPasswordState.error}
                          </p>
                        )}
                        <Button
                          type="submit"
                          size="sm"
                          disabled={resetPasswordState.isSubmitting}
                        >
                          {resetPasswordState.isSubmitting ? "Saving…" : "Save"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setResetPasswordState(null)}
                        >
                          Cancel
                        </Button>
                      </form>
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* ------------------------------------------------------------------ */}
      {/* Delete confirmation dialog                                          */}
      {/* ------------------------------------------------------------------ */}
      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete user "{deleteTarget?.username}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the account. Their jobs will be orphaned
              and become visible to admins only — no diagnostic data is deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={isDeleting}
              onClick={() => void handleDeleteConfirm()}
            >
              {isDeleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
