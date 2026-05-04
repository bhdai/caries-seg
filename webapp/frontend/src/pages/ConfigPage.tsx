/**
 * ConfigPage — Step 2 of the inference workflow.
 *
 * Displays:
 *   - A summary of the files chosen on UploadPage.
 *   - A pipeline radio group: "Single Stage" / "Two Stage".
 *   - A model architecture dropdown filtered by pipeline selection:
 *       Single Stage → UNet, Double-UNet
 *       Two Stage    → UNet, Double-UNet  (AttentionUNet excluded per plan)
 *   - A "Run Inference" button that submits the job and navigates to
 *     /result/:id on success.
 *
 * If the user lands here without any files in the store (e.g. hard refresh),
 * they are redirected back to /upload.
 *
 * NOTE: AttentionUNet is excluded from both pipelines.  The plan states:
 *   "No AttentionUNet for single-stage… we will not include attentionUnet in
 *    the webapp for 2 stage as well"
 */
import { createJob } from "@/api/jobs";
import type { ModelArch, PipelineType } from "@/api/types";
import { PatientCombobox } from "@/components/patients/PatientCombobox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUploadStore } from "@/context/UploadStore";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function ConfigPage() {
  const { files, setLastJobId } = useUploadStore();
  const navigate = useNavigate();
  const { t } = useTranslation();

  // ARCH_OPTIONS labels are translated — must be defined inside the component
  // so that `t` is in scope and re-evaluates when the locale changes.
  const ARCH_OPTIONS: { value: ModelArch; label: string }[] = [
    { value: "unet", label: t("job.model.unet") },
    { value: "double_unet", label: t("job.model.doubleUnet") },
  ];

  const [pipeline, setPipeline] = useState<PipelineType>("single_stage");
  const [arch, setArch] = useState<ModelArch>("unet");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [selectedPatientName, setSelectedPatientName] = useState<string | null>(null);

  // Guard: redirect to upload page if there are no files.
  useEffect(() => {
    if (files.length === 0) {
      navigate("/upload", { replace: true });
    }
  }, [files, navigate]);

  // Reset arch to unet when pipeline changes (safe default for both).
  useEffect(() => {
    setArch("unet");
  }, [pipeline]);

  async function handleSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      const job = await createJob(files, pipeline, arch, selectedPatientId ?? undefined);
      setLastJobId(job.id);
      navigate(`/result/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t("config.title")}</h1>
        <p className="text-muted-foreground mt-1">
          {t("config.subtitle", { count: files.length })}
        </p>
      </div>

      {/* Patient selection — optional, links this job to a patient record */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("config.patientTitle")}</CardTitle>
          <CardDescription>{t("config.patientDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <PatientCombobox
            value={selectedPatientId}
            valueName={selectedPatientName}
            onChange={(id, name) => {
              setSelectedPatientId(id);
              setSelectedPatientName(name);
            }}
          />
          {!selectedPatientId && (
            <p className="text-xs text-muted-foreground">
              {t("config.patientHint")}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Pipeline selection */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("config.pipelineTitle")}</CardTitle>
          <CardDescription>
            {t("config.pipelineDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3">
            {(
              [
                { value: "single_stage", label: t("config.pipelineSingle") },
                { value: "two_stage", label: t("config.pipelineTwo") },
              ] as const
            ).map(({ value, label }) => (
              <label
                key={value}
                className="flex items-center gap-3 cursor-pointer"
              >
                <input
                  type="radio"
                  name="pipeline"
                  value={value}
                  checked={pipeline === value}
                  onChange={() => setPipeline(value)}
                  className="accent-primary h-4 w-4"
                />
                <span className="text-sm font-medium">{label}</span>
              </label>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Model architecture */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("config.modelArchitectureLabel")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label htmlFor="arch-select">{t("config.architectureLabel")}</Label>
            <Select
              value={arch}
              onValueChange={(v) => setArch(v as ModelArch)}
            >
              <SelectTrigger id="arch-select" className="w-full">
                <SelectValue placeholder={t("config.architecturePlaceholder")} />
              </SelectTrigger>
              <SelectContent>
                {ARCH_OPTIONS.map(({ value, label }) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Actions */}
      <div className="flex justify-between">
        <Button variant="outline" onClick={() => navigate("/upload")} disabled={submitting}>
          {t("config.back")}
        </Button>
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting ? t("config.submitting") : t("config.submit")}
        </Button>
      </div>
    </div>
  );
}
