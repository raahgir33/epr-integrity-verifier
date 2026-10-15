"use client";

const BUTTON =
  "px-2 py-2.5 font-medium outline-none transition-colors duration-150 focus-visible:outline-solid focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary";
const ACTIVE = "bg-primary text-primary-foreground";
const IDLE = "bg-surface text-ink";

/** The EN/HI switch above a memo, shared by both letter components
 * (T17 — it was duplicated verbatim in each).
 *
 * When no Hindi draft exists the pair still renders, with HI disabled and
 * a short reason beside it. Hiding the switch entirely, as it did before,
 * read as "this memo was always English-only" — but a processor that has
 * just been through a live verification loses its Hindi draft, because
 * the live path writes the English memo only (app/events/
 * run_processor.py) after deleting the snapshot's two rows. The nightly
 * reset restores it. A viewer who used the toggle a minute earlier needs
 * to be told that, not shown a different set of controls. */
export function MemoLangToggle({
  lang,
  hasHindi,
  loadingHi,
  onSelect,
}: {
  lang: "en" | "hi";
  hasHindi: boolean;
  loadingHi: boolean;
  onSelect: (next: "en" | "hi") => void;
}) {
  const unavailable = "Hindi version available after the nightly refresh";
  return (
    <div className="flex items-center gap-2">
      <div className="flex overflow-hidden rounded border border-border">
        <button
          type="button"
          onClick={() => onSelect("en")}
          className={`${BUTTON} ${lang === "en" ? ACTIVE : IDLE}`}
        >
          EN
        </button>
        <button
          type="button"
          onClick={() => onSelect("hi")}
          disabled={loadingHi || !hasHindi}
          title={hasHindi ? undefined : unavailable}
          aria-label={hasHindi ? "Hindi" : unavailable}
          className={`${BUTTON} disabled:cursor-not-allowed disabled:opacity-60 ${
            lang === "hi" ? ACTIVE : IDLE
          }`}
        >
          {loadingHi ? "…" : "HI"}
        </button>
      </div>
      {hasHindi ? null : <span className="text-ink-muted">{unavailable}</span>}
    </div>
  );
}
