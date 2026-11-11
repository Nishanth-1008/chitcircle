/** @type {import('next').NextConfig} */
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// The FastAPI backend has no CORS middleware, so the browser talks to same-origin /api/backend/* and Next
// proxies a fixed allow-list of paths to the backend. `/webhooks/*` is deliberately NOT proxied: provider
// callbacks are server-to-server only.
const backend = (process.env.CHITCIRCLE_API_URL || '').replace(/\/$/, '');

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  async rewrites() {
    if (!backend) return [];
    return ['health', 'config', 'auth', 'circles', 'cycles', 'settlements', 'ledger', 'collections', 'sandbox',
      'proposed-actions', 'mandates'].flatMap((p) => [
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
