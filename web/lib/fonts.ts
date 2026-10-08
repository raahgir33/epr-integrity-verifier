import { IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import localFont from "next/font/local";

export const headingFont = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-heading",
  display: "swap",
});

export const bodyFont = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});

// Amendment 3 (T12 plan): loaded locally (not Google Fonts) so Hindi text
// renders correctly regardless of the viewer's OS/device fonts. Applied
// only to elements marked lang="hi" (globals.css's :lang(hi) rule) — not
// the whole app, so English body copy keeps bodyFont.
export const devanagariFont = localFont({
  src: "../public/fonts/NotoSansDevanagari-Regular.ttf",
  variable: "--font-devanagari",
  display: "swap",
});
