/** Build-time configuration. Nothing secret lives here; the backend URL is server-side only (next.config.mjs). */
export const API_BASE = '/api/backend';
export const DEFAULT_CURRENCY = process.env.NEXT_PUBLIC_DEFAULT_CURRENCY || 'INR';
