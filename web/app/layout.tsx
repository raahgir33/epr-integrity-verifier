import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EPR Integrity Verifier",
  description: "Independent verification of plastic packaging EPR certificates.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
