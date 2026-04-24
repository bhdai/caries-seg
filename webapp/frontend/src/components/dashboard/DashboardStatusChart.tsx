// =============================================================================
// DashboardStatusChart
// =============================================================================
//
// Encapsulates the compact status-distribution bar chart shown on the
// Dashboard.  The chart renders a horizontal stacked bar so the relative
// weight of each status is immediately visible even when the total count is
// small.
//
// This component is a pure presentation layer — it receives already-normalised
// chart data from `DashboardStatusOverview` and does not fetch anything itself.

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type { DashboardStatusSummary } from "@/api/types";
import { Bar, BarChart, XAxis, YAxis } from "recharts";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface DashboardStatusChartProps {
  summary: DashboardStatusSummary;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Render a compact horizontal stacked bar showing the distribution of all
 * historical jobs across the four lifecycle statuses.
 *
 * An empty chart (total === 0) is handled gracefully with a short message
 * rather than an empty canvas.
 */
export function DashboardStatusChart({ summary }: DashboardStatusChartProps) {
  if (summary.total === 0) {
    return (
      <p className="text-xs text-muted-foreground text-center py-4">
        No jobs yet — status distribution will appear here.
      </p>
    );
  }

  // Build a recharts-compatible single-row dataset.  Each status becomes one
  // key so all four segments can be stacked in a single Bar element group.
  const barData = [
    {
      name: "Distribution",
      pending: summary.pending,
      processing: summary.processing,
      completed: summary.completed,
      failed: summary.failed,
    },
  ];

  // Map status keys to the ChartContainer config format so the tooltip and
  // legend labels use the human-readable labels and themed colours.
  const chartConfig = Object.fromEntries(
    summary.chartData.map(({ status, label, colorToken }) => [
      status,
      { label, color: colorToken },
    ]),
  );

  return (
    <ChartContainer config={chartConfig} className="h-12 w-full">
      <BarChart
        data={barData}
        layout="vertical"
        barCategoryGap={0}
        margin={{ top: 0, right: 0, bottom: 0, left: 0 }}
      >
        {/* No visible axes — the stacked bar speaks for itself */}
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="name" hide />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={() => "All jobs"}
              formatter={(value, name) => [
                value,
                chartConfig[name as string]?.label ?? name,
              ]}
            />
          }
        />
        {summary.chartData.map(({ status, colorToken }) => (
          <Bar
            key={status}
            dataKey={status}
            stackId="distribution"
            fill={colorToken}
            radius={0}
          />
        ))}
      </BarChart>
    </ChartContainer>
  );
}
