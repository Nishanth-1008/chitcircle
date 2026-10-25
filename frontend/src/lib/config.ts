/** Build-time configuration. Nothing secret lives here; the backend URL is server-side only (next.config.mjs). */
export const LIVE_API_ENABLED = process.env.NEXT_PUBLIC_LIVE_API_ENABLED === 'true';
export const API_BASE = '/api/backend';
export const DEFAULT_CURRENCY = process.env.NEXT_PUBLIC_DEFAULT_CURRENCY || 'INR';
/** "stub" until a real, verified provider integration exists. Drives the honest payout notices. */
export const PAYOUT_GATEWAY: 'stub' | 'live' = process.env.NEXT_PUBLIC_PAYOUT_GATEWAY === 'live' ? 'live' : 'stub';
