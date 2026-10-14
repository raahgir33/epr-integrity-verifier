import { Google_Sans, Google_Sans_Code, Inter } from "next/font/google";
import localFont from "next/font/local";

// T13.5c plan, Batch 0.14: Google Sans replaces Source Serif 4 (headings)
// and IBM Plex Sans (body) for all English text, per the developer's
// deployed-site review — both are confirmed present in next/font/google's
// bundled Google Fonts data (checked directly in
// node_modules/next/dist/compiled/@next/font/dist/google/font-data.json
// before writing this), so no substitution was needed.
export const headingFont = Google_Sans({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-heading",
  display: "swap",
});

export const bodyFont = Google_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});

// Monospace (reasoning tool calls, document/processor IDs) — Google Sans
// Code, same batch.
export const monoFont = Google_Sans_Code({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono-code",
  display: "swap",
});

// T16a O2: Inter, for the hero HUD chips' figure line only, at the
// developer's request. Scoped deliberately — --font-sans/-display stay
// Google Sans everywhere else, and this is exposed as its own `font-ui`
// utility rather than being folded into an existing token, so nothing
// else picks it up by accident. Confirmed present in next/font/google's
// bundled data before writing this, the same check the Google Sans swap
// used.
export const uiFont = Inter({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-ui-figure",
  display: "swap",
});

// Amendment 3 (T12 plan): loaded locally (not Google Fonts) so Hindi text
// renders correctly regardless of the viewer's OS/device fonts. Applied
// only to elements marked lang="hi" (globals.css's :lang(hi) rule) — not
// the whole app, so English body copy keeps bodyFont. Untouched by the
// T13.5c font swap, per the developer's note.
export const devanagariFont = localFont({
  src: "../public/fonts/NotoSansDevanagari-Regular.ttf",
  variable: "--font-devanagari",
  display: "swap",
});
