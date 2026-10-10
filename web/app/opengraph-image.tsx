import { ImageResponse } from "next/og";

export const alt = "EPR Integrity Verifier";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// T13.8: generated from the same navy/teal palette as the rest of the
// app (globals.css's dark-mode tokens), not a static design asset — one
// shared default image for link previews across every route.
export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          background: "#071952",
          color: "#f4f4f4",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", width: 72, height: 6, background: "#00b7b5", marginBottom: 40 }} />
        <div style={{ display: "flex", fontSize: 64, fontWeight: 700 }}>EPR Integrity Verifier</div>
        <div style={{ display: "flex", fontSize: 28, color: "#959cb3", marginTop: 20 }}>
          Independent verification of plastic packaging EPR certificates
        </div>
      </div>
    ),
    { ...size }
  );
}
