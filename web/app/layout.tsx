import type { Metadata } from "next";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { PageContainer } from "@/components/ui/PageContainer";
import { bodyFont, devanagariFont, headingFont } from "@/lib/fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "EPR Integrity Verifier",
  description: "Independent verification of plastic packaging EPR certificates.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${bodyFont.variable} ${headingFont.variable} ${devanagariFont.variable}`}>
      <body className="flex min-h-screen flex-col bg-slate-50 font-sans text-slate-900">
        <Nav />
        <PageContainer className="flex-1 py-8">{children}</PageContainer>
        <Footer />
      </body>
    </html>
  );
}
