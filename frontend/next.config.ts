import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow accessing the dev server from other devices on the LAN (phones/laptops).
  // Add any LAN IP you open the app from here.
  allowedDevOrigins: ["192.168.118.16", "192.168.0.196"],
};

export default nextConfig;
