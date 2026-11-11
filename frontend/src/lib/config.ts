/** Build-time configuration. Nothing secret lives here.
 *
 * API_BASE is the base the API client fetches against. It defaults to the same-origin
 * Next proxy (`/api/backend/*`), which `next.config.mjs` rewrites to `CHITCIRCLE_API_URL`
 * — no CORS needed on the backend because the browser only ever hits the same origin.
 *
 * Override with `NEXT_PUBLIC_CHITCIRCLE_API_URL` to call a different origin directly
 * (that origin must allow CORS from the frontend origin). `CHITCIRCLE_API_URL` itself is
 * server-side only and drives the proxy target in next.config.mjs. */
export const API_BASE = process.env.NEXT_PUBLIC_CHITCIRCLE_API_URL || '/api/backend';
export const DEFAULT_CURRENCY = process.env.NEXT_PUBLIC_DEFAULT_CURRENCY || 'INR';
