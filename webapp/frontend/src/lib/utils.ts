/**
 * Utility: merge Tailwind class names without conflicts.
 *
 * This is the standard shadcn/ui helper.  `clsx` handles conditional and
 * array class arguments; `twMerge` resolves Tailwind conflicts so later
 * classes win (e.g. `cn("p-4", "p-2")` → `"p-2"`).
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
