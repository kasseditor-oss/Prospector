/** @type {import('next').NextConfig} */

// The desktop build is a different shape of app: FastAPI serves the pages and
// the API from one origin, so there is nothing to proxy and no Node runtime on
// the user's machine. The dev/server build keeps the rewrite.
const desktop = process.env.PROSPECTOR_DESKTOP === "1";

const nextConfig = desktop
  ? {
      output: "export",
      // Static export writes app/index.html rather than app.html, which is
      // what a plain file server can resolve without rewrite rules.
      trailingSlash: true,
      images: { unoptimized: true },
    }
  : {
      async rewrites() {
        // The browser talks to /api/* on its own origin; Next proxies to the
        // Python service. Keeps the API key server-side and avoids CORS.
        return [
          {
            source: "/api/:path*",
            destination: `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/api/:path*`,
          },
        ];
      },
      images: {
        remotePatterns: [{ protocol: "https", hostname: "yt3.ggpht.com" }],
      },
    };

export default nextConfig;
