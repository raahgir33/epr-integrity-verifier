import type { Metadata } from "next";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { ThemeProvider } from "@/components/ThemeProvider";
import { PageContainer } from "@/components/ui/PageContainer";
import { bodyFont, devanagariFont, headingFont, monoFont } from "@/lib/fonts";
import "./globals.css";

export const metadata: Metadata = {
  // T13.8: resolves the auto-generated opengraph-image/icon tags to an
  // absolute URL — without this, Next falls back to localhost:3000,
  // which breaks link previews once deployed. Same fixed production URL
  // CORS_ALLOWED_ORIGINS already hardcodes (api/.env.example) — this app
  // has one deployed Cloud Run URL, not a custom domain.
  metadataBase: new URL("https://epr-web-igr6jyk3na-el.a.run.app"),
  title: {
    default: "EPR Integrity Verifier",
    template: "%s — EPR Integrity Verifier",
  },
  description: "Independent verification of plastic packaging EPR certificates.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`antialiased ${bodyFont.variable} ${headingFont.variable} ${monoFont.variable} ${devanagariFont.variable}`}
    >
      <body className="flex min-h-screen flex-col bg-page font-sans text-ink">
        <ThemeProvider>
          <Nav />
          {/* T13.6b plan, Part 3: Nav is now fixed (overlays the landing
              page's full-bleed hero), out of document flow — every page
              needs this top padding to avoid sitting under it. Nav
              itself publishes --nav-h via ResizeObserver; the 4rem
              fallback matches Nav's own current rendered height for the
              instant before that JS runs. */}
          <main className="flex-1 pt-[var(--nav-h,4rem)]">
            <PageContainer className="py-8">{children}</PageContainer>
          </main>
          <Footer />
        </ThemeProvider>
      </body>
    </html>
  );
}
