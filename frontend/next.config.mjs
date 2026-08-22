/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // The browser talks to /api/* on its own origin; Next proxies to the
    // Python service. Keeps the API key server-side and avoids CORS in prod.
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
