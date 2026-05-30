import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 'standalone' mode creates a self-contained output in .next/standalone
  // This makes the Docker image ~80MB instead of ~1GB
  // The standalone output includes only the files needed to run the app
  output: 'standalone',

  async rewrites() {
    return [
      {
        // Proxy all /api/* requests to the backend container
        // In Docker, 'backend' is the service hostname (docker-compose service name)
        // Locally, falls back to 127.0.0.1:8001
        source: '/api/:path*',
        destination: `${process.env.BACKEND_INTERNAL_URL || 'http://13.206.196.149:8001'}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
