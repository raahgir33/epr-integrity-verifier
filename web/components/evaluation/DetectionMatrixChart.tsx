import { Check, X } from "lucide-react";
import { ChartPanel, FiguresTable } from "@/components/evaluation/ChartPanel";
import type { DetectionMatrix, DetectionRow } from "@/lib/evaluation";

/** A tick is never the only cue: the word beside it carries the same
 * meaning, so the cell reads correctly without colour or shape. Colour
 * comes from the risk tokens via CSS, so it is right on the first paint
 * in either theme. */
function Outcome({ row, ok }: { row: DetectionRow; ok: boolean }) {
  const word = row.kind === "pattern" ? (ok ? "Detected" : "Missed") : ok ? "None" : "Flagged";
  const Icon = ok ? Check : X;
  return (
    <span
      className={`inline-flex items-center gap-1 font-medium ${ok ? "text-risk-low" : "text-risk-high"}`}
    >
      <Icon aria-hidden="true" strokeWidth={2} className="size-3.5 shrink-0" />
      {word}
    </span>
  );
}

export function DetectionMatrixChart({ matrix }: { matrix: DetectionMatrix }) {
  const headers = ["Pattern", ...matrix.bases.map((basis) => basis.label)];

  return (
    <ChartPanel
      title="Detection by pattern"
      caption="Every pattern planted in the held-out dataset, and whether the system found all of its instances on each set of facts. The last two rows are the opposite test: whether anything clean was wrongly flagged."
      figures={
        <FiguresTable
          caption="Instances found out of instances planted, and processors flagged out of processors checked."
          headers={headers}
        >
          {matrix.rows.map((row) => (
            <tr key={row.name} className="border-b border-border/60 last:border-0">
              <th scope="row" className="py-1.5 pr-3 font-normal text-ink">
                {row.name}
              </th>
              {matrix.bases.map((basis) => {
                const cell = row.cells.find((c) => c.factsSource === basis.factsSource);
                return (
                  <td
                    key={basis.factsSource}
                    className="py-1.5 pr-3 text-right tabular-nums text-ink-muted"
                  >
                    {cell ? cell.detail : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </FiguresTable>
      }
    >
      <div className="overflow-x-auto" role="region" aria-label="Detection by pattern, table" tabIndex={0}>
        <table className="w-full border-collapse text-left text-xs">
          <caption className="sr-only">
            Detection outcome for each planted pattern, by facts source.
          </caption>
          <thead>
            <tr className="border-b border-border">
              {headers.map((header, index) => (
                <th
                  key={header}
                  scope="col"
                  className={`py-2 pr-3 font-medium text-ink-muted ${index > 0 ? "text-right" : ""}`}
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row) => (
              <tr key={row.name} className="border-b border-border/60 last:border-0">
                <th scope="row" className="py-2 pr-3 font-normal text-ink">
                  {row.name}
                </th>
                {matrix.bases.map((basis) => {
                  const cell = row.cells.find((c) => c.factsSource === basis.factsSource);
                  return (
                    <td key={basis.factsSource} className="py-2 pr-3 text-right">
                      {cell ? (
                        <Outcome row={row} ok={cell.ok} />
                      ) : (
                        <span className="text-ink-muted">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartPanel>
  );
}
