/**
 * OpacitySlider
 *
 * Thin wrapper around the shadcn Slider for controlling mask overlay opacity.
 *
 * Props:
 *   value    — current opacity value in [0, 100].
 *   onChange — called whenever the slider is moved.
 */
import { Slider } from "@/components/ui/slider";

interface OpacitySliderProps {
  value: number;
  onChange: (value: number) => void;
}

export function OpacitySlider({ value, onChange }: OpacitySliderProps) {
  return (
    <div className="flex items-center gap-3 w-full max-w-xs">
      <span className="text-sm text-muted-foreground shrink-0">Opacity</span>
      <Slider
        min={0}
        max={100}
        step={1}
        value={[value]}
        onValueChange={([v]) => onChange(v)}
        aria-label="Mask overlay opacity"
        className="flex-1"
      />
      <span className="text-sm text-muted-foreground w-8 text-right shrink-0">
        {value}%
      </span>
    </div>
  );
}
