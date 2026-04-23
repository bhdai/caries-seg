/**
 * ImageThumbnail
 *
 * Shows a preview thumbnail for an image file.  Used in two contexts:
 *   1. UploadPage — previews a client-side File object before submission.
 *   2. ResultPage — previews a processed result using an object URL.
 *
 * Props:
 *   src      — URL string (object URL or API URL).
 *   label    — filename displayed below the image.
 *   onRemove — optional callback rendered as an × button (upload preview only).
 */
import { X } from "lucide-react";

interface ImageThumbnailProps {
  src: string;
  label: string;
  onRemove?: () => void;
}

export function ImageThumbnail({ src, label, onRemove }: ImageThumbnailProps) {
  return (
    <div className="relative flex flex-col items-center gap-1 w-28">
      <div className="relative w-28 h-20 rounded-md overflow-hidden border bg-muted">
        <img
          src={src}
          alt={label}
          className="w-full h-full object-cover"
        />
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="absolute top-1 right-1 rounded-full bg-background/80 p-0.5 hover:bg-background transition-colors"
            aria-label={`Remove ${label}`}
          >
            <X className="w-3 h-3 text-foreground" />
          </button>
        )}
      </div>
      <span
        className="text-xs text-muted-foreground text-center w-full truncate"
        title={label}
      >
        {label}
      </span>
    </div>
  );
}
