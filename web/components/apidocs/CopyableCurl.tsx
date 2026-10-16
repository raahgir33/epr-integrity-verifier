"use client";

import { Check, Copy } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

/** A runnable example with a copy button. The page never calls the API
 * itself — nothing here fires a request, which matters most for the one
 * endpoint that would start real work.
 *
 * The icon swap follows the pattern Nav's menu button already uses:
 * cross-faded with scale and blur rather than toggled, `initial={false}`
 * so nothing animates on first paint, and spring with no bounce. */
export function CopyableCurl({ command, warning }: { command: string; warning?: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access denied by the browser — nothing to recover
      // from; the button simply stays inert and the command is still
      // selectable by hand.
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Example</p>
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? "Example copied" : "Copy example"}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-ink-muted outline-none transition-[color,scale] duration-150 hover:text-ink focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-safe:active:scale-[0.96]"
        >
          <span className="relative inline-flex size-3.5 shrink-0 items-center justify-center">
            <AnimatePresence initial={false} mode="popLayout">
              <motion.span
                key={copied ? "copied" : "idle"}
                initial={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
                animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                exit={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
                transition={{ type: "spring", duration: 0.3, bounce: 0 }}
                className="inline-flex"
              >
                {copied ? (
                  <Check aria-hidden="true" strokeWidth={1.5} className="size-3.5" />
                ) : (
                  <Copy aria-hidden="true" strokeWidth={1.5} className="size-3.5" />
                )}
              </motion.span>
            </AnimatePresence>
          </span>
          {/* The word changes with the icon, so the state never depends
              on the glyph alone. Fixed width keeps the button from
              resizing as the label swaps. */}
          <span className="inline-block w-12 text-left">{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      {warning ? (
        <p className="mb-1.5 border-l-2 border-risk-high/60 pl-2 text-xs font-medium text-ink">
          {warning}
        </p>
      ) : null}
      {/* A long command scrolls sideways on a narrow screen, so the block
          is focusable and named — otherwise a keyboard user cannot reach
          the end of the line. */}
      <pre
        className="overflow-x-auto rounded-sm bg-surface-sunk p-3 font-mono text-xs leading-relaxed text-ink outline-none focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        role="region"
        aria-label="Example request"
        tabIndex={0}
      >
        <code>{command}</code>
      </pre>
    </div>
  );
}
