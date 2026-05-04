// =============================================================================
// PatientCombobox
// =============================================================================
//
// Controlled combobox for selecting a patient by name or phone.  Used by:
//   - ConfigPage          — link a patient when submitting a new job.
//   - PatientLinkModal    — retroactively link a job to a patient.
//   - HistoryFilters      — filter the job list by patient.
//
// UI pattern: shadcn Popover + cmdk Command for a keyboard-navigable
// typeahead with "Create '[query]'" as a zero-results escape hatch.
//
// When the user types a name that returns no matches, a "Create '[query]'"
// item is shown at the bottom of the list.  Clicking it opens
// PatientCreateModal pre-filled with the typed name.  On successful creation
// the new patient is auto-selected.
//
// A "×" clear button is rendered on the trigger when a patient is selected
// so the user can remove the selection without reopening the dropdown.

import { usePatientSearchQuery } from "@/hooks/usePatientSearchQuery";
import type { PatientSummary } from "@/api/patients";
import { PatientCreateModal } from "@/components/patients/PatientCreateModal";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";
import { ChevronsUpDown, Loader2, PlusCircle, X } from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PatientComboboxProps {
  /** Currently selected patient UUID, or null when no patient is selected. */
  value: string | null;
  /** Display name for the currently selected patient. */
  valueName?: string | null;
  /** Called with the new patient UUID (or null to clear) when selection changes. */
  onChange: (patientId: string | null, patientName: string | null) => void;
  /** Extra class names for the trigger button. */
  className?: string;
  /** Placeholder text shown when no patient is selected. */
  placeholder?: string;
  /** Whether the combobox is disabled. */
  disabled?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Debounced patient search combobox.
 *
 * The popover only fires the search query while it is open (`enabled` flag
 * passed to usePatientSearchQuery), avoiding unnecessary network requests
 * when the field is not being interacted with.
 */
export function PatientCombobox({
  value,
  valueName,
  onChange,
  className,
  placeholder,
  disabled = false,
}: PatientComboboxProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // Only run the search while the popover is open to avoid background queries.
  const { data: results, isLoading } = usePatientSearchQuery(search, open);

  const resolvedPlaceholder =
    placeholder ?? t("patient.combobox.placeholder");

  // When a patient row is selected from the list, update parent state and
  // close the popover.
  const handleSelect = useCallback(
    (patient: PatientSummary) => {
      onChange(patient.id, patient.full_name);
      setOpen(false);
      setSearch("");
    },
    [onChange],
  );

  // Clear the current selection.
  const handleClear = useCallback(
    (e: React.MouseEvent) => {
      // Stop propagation so the clear click does not toggle the popover open.
      e.stopPropagation();
      onChange(null, null);
    },
    [onChange],
  );

  // Called by PatientCreateModal after a patient is successfully created.
  const handleCreated = useCallback(
    (id: string, name: string) => {
      onChange(id, name);
      setCreateModalOpen(false);
      setOpen(false);
      setSearch("");
    },
    [onChange],
  );

  const showCreateOption = search.length >= 1 && results.length === 0 && !isLoading;

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className={cn(
              "w-full justify-between font-normal",
              !value && "text-muted-foreground",
              className,
            )}
          >
            <span className="truncate">
              {value && valueName ? valueName : resolvedPlaceholder}
            </span>
            <span className="flex items-center ml-2 shrink-0">
              {/* Clear button — only visible when a patient is selected */}
              {value && (
                <span
                  role="button"
                  aria-label={t("patient.combobox.clear")}
                  tabIndex={0}
                  onClick={handleClear}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") handleClear(e as unknown as React.MouseEvent);
                  }}
                  className="mr-1 rounded-sm opacity-70 hover:opacity-100 focus:outline-none focus:ring-1 focus:ring-ring cursor-pointer"
                >
                  <X className="h-4 w-4" />
                </span>
              )}
              <ChevronsUpDown className="h-4 w-4 opacity-50" />
            </span>
          </Button>
        </PopoverTrigger>

        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput
              placeholder={t("patient.combobox.searchPlaceholder")}
              value={search}
              onValueChange={setSearch}
            />
            <CommandList>
              {/* Loading indicator */}
              {isLoading && (
                <div className="py-4 flex justify-center">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              )}

              {/* Search results */}
              {!isLoading && results.length > 0 && (
                <CommandGroup>
                  {results.map((patient) => (
                    <CommandItem
                      key={patient.id}
                      value={patient.id}
                      onSelect={() => handleSelect(patient)}
                    >
                      <div className="flex flex-col">
                        <span className="font-medium">{patient.full_name}</span>
                        {patient.phone && (
                          <span className="text-xs text-muted-foreground">
                            {patient.phone}
                          </span>
                        )}
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}

              {/* Empty state — prompt to create */}
              {!isLoading && search.length >= 1 && results.length === 0 && (
                <CommandEmpty>
                  {t("patient.combobox.noResults")}
                </CommandEmpty>
              )}

              {/* Prompt to start typing */}
              {!isLoading && search.length === 0 && (
                <CommandEmpty>
                  {t("patient.combobox.typeToSearch")}
                </CommandEmpty>
              )}

              {/* "Create '[query]'" option — shown when search has no matches */}
              {showCreateOption && (
                <CommandGroup>
                  <CommandItem
                    value={`__create__${search}`}
                    onSelect={() => {
                      setOpen(false);
                      setCreateModalOpen(true);
                    }}
                    className="text-primary"
                  >
                    <PlusCircle className="mr-2 h-4 w-4" />
                    {t("patient.combobox.createOption", { name: search })}
                  </CommandItem>
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {/* Quick-create modal — opened from the "Create '[query]'" option */}
      <PatientCreateModal
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
        defaultName={search}
        onCreated={handleCreated}
      />
    </>
  );
}
