import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

// T13.8: generated, not a static file — same navy/teal palette as
// globals.css's dark-mode tokens (--color-page / --color-primary), fixed
// regardless of the viewer's OS theme since a favicon doesn't switch.
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#071952",
          color: "#00b7b5",
          fontSize: 22,
          fontWeight: 700,
          fontFamily: "sans-serif",
        }}
      >
        E
      </div>
    ),
    { ...size }
  );
}
