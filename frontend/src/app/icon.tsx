import { ImageResponse } from "next/og";

export const size = { width: 220, height: 68 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "white",
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "flex-end",
          paddingBottom: 10,
          paddingLeft: 12,
          fontWeight: 900,
          fontSize: 46,
          letterSpacing: -1,
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <span style={{ color: "#0a6cb0" }}>erp</span>
        <span style={{ color: "#29a9e0" }}>SOFT</span>
        <span style={{ color: "#0a6cb0" }}>app</span>
      </div>
    ),
    { ...size }
  );
}
