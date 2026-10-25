/** @type {import('next').NextConfig} */

// The FastAPI backend has no CORS middleware and uses a header-based auth stub, so the browser talks to
// same-origin /api/backend/* and Next proxies a fixed allow-list of paths to the backend.
// `/webhooks/*` is deliberately NOT proxied: provider callbacks are server-to-server only.
const backend = (process.env.CHITCIRCLE_API_URL || '').replace(/\/$/, '');

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    if (!backend) return [];
    return ['health', 'circles', 'cycles', 'settlements', 'ledger'].flatMap((p) => [
      { source: `/api/backend/${p}`, destination: `${backend}/${p}` },
      { source: `/api/backend/${p}/:path*`, destination: `${backend}/${p}/:path*` },
    ]);
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-Frame-Options', value: 'DENY' },
        ],
      },
    ];
  },
};

export default nextConfig;
