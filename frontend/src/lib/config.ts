/** Build-time configuration. Nothing secret lives here.
 *
 * API_BASE is the base the API client fetches against. It is always the same-origin
 * Next proxy (`/api/backend/*`), which `next.config.mjs` rewrites to `CHITCIRCLE_API_URL`
 * — no CORS needed on the backend because the browser only ever hits the same origin.
 *
 * `CHITCIRCLE_API_URL` is server-side only and drives the proxy target in next.config.mjs.
 * It must be set in the hosting platform's project environment variables (e.g. Vercel).
 */
export const API_BASE = '/api/backend';
export const DEFAULT_CURRENCY = process.env.NEXT_PUBLIC_DEFAULT_CURRENCY || 'INR';
