import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // A 10 MiB PDF plus multipart metadata must fit through the API rewrite.
    proxyClientMaxBodySize: 11 * 1024 * 1024,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/:path*` }];
  },
  poweredByHeader: false,
};

export default nextConfig;
