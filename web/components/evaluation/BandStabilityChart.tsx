import { ChartPanel, FiguresTable } from "@/components/evaluation/ChartPanel";
import type { BandStability } from "@/lib/evaluation";

/** Risk tokens via CSS rather than literal hex, so a cell is the right
 * colour on the server's first paint in either theme. Each cell also
 * carries its band in words, so colour is never the only cue. */
function bandClasses(band: string | null): string {
  switch (band) {
    case "Low":
      return "text-risk-low border-risk-low";
    case "Medium":
      return "text-risk-medium border-risk-medium";
    case "High":
      return "text-risk-high border-risk-high";
    default:
      return "text-risk-unknown border-risk-unknown";
  }
}

export function BandStabilityChart({ stability }: { stability: BandStability }) {
  const headers = ["Processor", ...stability.runs.map((run) => `Run ${run}`)];

  return (
    <ChartPanel
      title="Risk-band stability across repeat runs"
      caption="The band each processor was assessed at in three identical re-runs on extracted facts. A row holding one colour and one word throughout is a processor the agents judged the same way every time."
      figures={
        <FiguresTable
          caption="Assessed risk band per processor, per run, on extracted facts across three runs."
          headers={headers}
        >
          {stability.rows.map((row) => (
            <tr key={row.processorId} className="border-b border-border/60 last:border-0">
              <th scope="row" className="py-1.5 pr-3 font-normal text-ink">
                {row.processorId}
              </th>
              {row.cells.map((cell) => (
                <td key={cell.run} className="py-1.5 pr-3 text-right text-ink-muted">
                  {cell.band ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </FiguresTable>
      }
    >
      <div className="overflow-x-auto" role="region" aria-label="Risk-band stability across repeat runs, table" tabIndex={0}>
        <table className="w-auto border-collapse text-left text-xs">
          <caption className="sr-only">
            Assessed risk band for each processor in each of three identical re-runs on extracted
            facts.
          </caption>
          <thead>
            <tr className="border-b border-border">
              {headers.map((header, index) => (
                <th
                  key={header}
                  scope="col"
                  className={`py-2 font-medium text-ink-muted ${index > 0 ? "px-3 text-center" : "pr-6"}`}
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stability.rows.map((row) => (
              <tr key={row.processorId} className="border-b border-border/60 last:border-0">
                <th scope="row" className="py-1.5 pr-6 font-normal text-ink">
                  {row.processorId}
                </th>
                {row.cells.map((cell) => (
                  <td key={cell.run} className="px-3 py-1.5 text-center">
                    <span
                      className={`inline-flex min-w-16 justify-center rounded-sm border bg-surface-sunk px-2 py-1 font-medium ${bandClasses(cell.band)}`}
                    >
                      {cell.band ?? "—"}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        Extracted Facts, 3 Runs. Each Cell Carries Its Band in Words, so the Colour Is Never the
        Only Cue.
      </p>
    </ChartPanel>
  );
}
