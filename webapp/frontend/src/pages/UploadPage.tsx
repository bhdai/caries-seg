/**
 * UploadPage — Step 1 of the inference workflow.
 *
 * Lets the user drag-and-drop (or click to select) one or more panoramic
 * dental X-ray images (JPEG / PNG, max 20 MB each).  Client-side
 * previews are generated via URL.createObjectURL so no network round-trip
 * is needed.
 *
 * Validated files are stored in the UploadStore context so ConfigPage can
 * read them on the next step.
 *
 * File constraints:
 *   - MIME: image/jpeg, image/png
 *   - Size: < 10 MB per file
 */
import { ImageThumbnail } from "@/components/ImageThumbnail";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useUploadStore } from "@/context/UploadStore";
import { UploadCloud } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { type FileRejection, useDropzone } from "react-dropzone";
import { useNavigate } from "react-router-dom";

const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
const ACCEPTED_MIME = { "image/jpeg": [], "image/png": [] };

interface Preview {
  file: File;
  objectUrl: string;
}

export default function UploadPage() {
  const { files, setFiles } = useUploadStore();
  const navigate = useNavigate();

  const [previews, setPreviews] = useState<Preview[]>([]);
  const [errors, setErrors] = useState<string[]>([]);

  // Keep a ref to all object URLs created so we can revoke them on unmount.
  const objectUrlsRef = useRef<string[]>([]);

  // Hydrate the preview list from the store when the user navigates back
  // to this route.  The store still holds the previously selected File
  // objects, but local preview state starts empty on remount.  We create
  // new object URLs here once, on mount only, so the thumbnails reappear.
  useEffect(() => {
    if (files.length === 0) return;
    const hydrated: Preview[] = files.map((file) => {
      const objectUrl = URL.createObjectURL(file);
      objectUrlsRef.current.push(objectUrl);
      return { file, objectUrl };
    });
    setPreviews(hydrated);
    // Intentionally runs once on mount; we do not re-sync on every files
    // change because local preview edits (remove) should not be overwritten.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      // Revoke object URLs when the component unmounts to avoid memory leaks.
      for (const url of objectUrlsRef.current) {
        URL.revokeObjectURL(url);
      }
    };
  }, []);

  const onDrop = useCallback((accepted: File[], rejected: FileRejection[]) => {
    const newErrors: string[] = [];

    if (rejected.length > 0) {
      for (const { file, errors: errs } of rejected) {
        for (const err of errs) {
          if (err.code === "file-too-large") {
            newErrors.push(`"${file.name}" exceeds 10 MB.`);
          } else if (err.code === "file-invalid-type") {
            newErrors.push(`"${file.name}" is not a JPEG or PNG.`);
          } else {
            newErrors.push(`"${file.name}": ${err.message}`);
          }
        }
      }
    }

    setErrors(newErrors);

    if (accepted.length === 0) return;

    const newPreviews: Preview[] = accepted.map((file) => {
      const objectUrl = URL.createObjectURL(file);
      objectUrlsRef.current.push(objectUrl);
      return { file, objectUrl };
    });

    setPreviews((prev) => {
      // Deduplicate by file name + size + lastModified.
      const existing = new Set(
        prev.map((p) => `${p.file.name}:${p.file.size}:${p.file.lastModified}`),
      );
      const unique = newPreviews.filter(
        (p) =>
          !existing.has(
            `${p.file.name}:${p.file.size}:${p.file.lastModified}`,
          ),
      );
      return [...prev, ...unique];
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_MIME,
    maxSize: MAX_SIZE_BYTES,
    multiple: true,
  });

  function removePreview(index: number) {
    setPreviews((prev) => {
      URL.revokeObjectURL(prev[index].objectUrl);
      return prev.filter((_, i) => i !== index);
    });
  }

  function handleContinue() {
    setFiles(previews.map((p) => p.file));
    navigate("/config");
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Upload X-rays</h1>
        <p className="text-muted-foreground mt-1">
          Drag and drop one or more panoramic dental radiographs to begin.
        </p>
      </div>

        {/* Drop zone */}
        <Card>
          <CardContent className="p-0">
            <div
              {...getRootProps()}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-10 text-center transition-colors ${
                isDragActive
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/30 hover:border-primary/60"
              }`}
            >
              <input {...getInputProps()} />
              <UploadCloud className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
              {isDragActive ? (
                <p className="text-sm font-medium">Drop the files here…</p>
              ) : (
                <>
                  <p className="text-sm font-medium">
                    Click or drag files here
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    JPEG or PNG · max 10 MB each
                  </p>
                </>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Validation errors */}
        {errors.length > 0 && (
          <Alert variant="destructive">
            <AlertDescription>
              <ul className="list-disc list-inside space-y-1">
                {errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {/* Previews */}
        {previews.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-3">
              {previews.length} file{previews.length > 1 ? "s" : ""} selected
            </p>
            <div className="flex flex-wrap gap-3">
              {previews.map((p, i) => (
                <ImageThumbnail
                  key={`${p.file.name}-${p.file.lastModified}`}
                  src={p.objectUrl}
                  label={p.file.name}
                  onRemove={() => removePreview(i)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Continue */}
        <div className="flex justify-end">
          <Button
            disabled={previews.length === 0}
            onClick={handleContinue}
          >
            Continue
          </Button>
        </div>
    </div>
  );
}
