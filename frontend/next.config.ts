import type { NextConfig } from "next";
import path from "path";
import { config as loadEnv } from "dotenv";

// Load the shared root .env (one level above frontend/) so both the engine
// and the frontend read from the same file.
loadEnv({ path: path.resolve(__dirname, "../.env"), override: false });

const nextConfig: NextConfig = {
  basePath: "/dataconv",
  // Allow accessing the dev server from other devices on the LAN (phones/laptops).
  // Add any LAN IP you open the app from here.
  allowedDevOrigins: ["192.168.118.16", "192.168.0.196"],
};

export default nextConfig;
