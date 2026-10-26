# 09. Clients: Web and Mobile

## 1. Strategy

| Surface | Technology | Role |
|---|---|---|
| Website and organizer console | **Next.js (App Router) + TypeScript** | Primary product surface; responsive; installable as a PWA; hosts the Bryntum timeline |
| Mobile app | **Expo (React Native) + TypeScript** | Member-first: pay, bid, approve, notifications, biometrics |
| Shared | **Generated API client** from OpenAPI, shared formatting and design tokens in a monorepo | One contract, no hand-written API types |

**Why Expo over alternatives.** It reuses TypeScript and React skills, ships over-the-air updates, and handles push, secure storage and deep links. Flutter would give one rendering engine but loses the shared TypeScript client and the React component knowledge. A Capacitor wrapper of the web app is a fallback if mobile must ship very fast, with weaker native feel.

**Bryntum is web-only.** The member-by-month timeline on web uses Bryntum Scheduler; on mobile it is a custom virtualized grid (FlashList) with the same data contract.

## 2. Web architecture

- **Next.js App Router** with server components for shell and marketing, client components for interactive views.
- **TanStack Query** for server state: caching, background refetch, optimistic updates only for non-financial actions.
- **Generated client** (`openapi-typescript` plus a thin fetch wrapper, or Orval) from `/openapi.json`. CI fails if the generated client is stale.
- **Forms** with React Hook Form and schema validation shared from the OpenAPI types.
- **Design system:** Tailwind with tokens, accessible primitives (Radix or similar), dark mode, RTL support.
- **Data grid:** the ledger and statements use a grid component (AG Grid is a sponsor option); virtualized, server-side pagination by cursor.
- **PWA:** service worker caches the shell and last-known read-only views; **payment and approval actions always require a live connection**.
- **Real-time:** polling in Phase 1, SSE in Phase 4.
- **Hosting:** Render or Vercel for the hackathon; CDN with immutable hashed assets.

## 3. Mobile architecture

- **Expo Router**, EAS Build and **EAS Update** for over-the-air JS updates (store review is still required for native changes).
- **Auth:** OIDC with phone OTP; tokens in secure storage; biometric gate for payout approvals and payment-detail changes.
- **Push:** Expo Notifications over FCM and APNs; deep links open the exact cycle, bid screen or approval.
- **Offline:** read-only cache of the last state; queue only non-financial actions (for example mark as read). Never queue a bid or approval offline.
- **Payments:** open PayPal-hosted flows in an in-app browser or the PayPal app; return via deep link; confirm by webhook-driven state, not by the redirect alone.
- **Performance:** FlashList for long lists, image and bundle budgets, Hermes engine.
- **Accessibility:** dynamic type, screen reader labels, sufficient contrast, large touch targets.

## 4. Key screens

| Screen | Organizer | Member |
|---|---|---|
| Home | Dashboard: paid, late, pending approvals, money at risk, next auction | Next payment, next auction, my balance in the circle |
| Timeline | Member x month grid (Bryntum on web) | My row highlighted, group status |
| Auction | Open and close, see bids (per mode) | Place bid with "what I receive" and effective rate preview |
| Settlement | Review, approve, release payout | See my dividend and net installment breakdown |
| Ledger | Full, filter, export | My entries; group-level summary |
| Approvals | One-tap queue of agent-proposed actions | Guarantor confirmations |
| Disputes | Open, assign, resolve | Flag an entry |
| Settings | Ruleset versions, jurisdiction profile, visibility tiers, notification policy | Language, channels, privacy |

## 5. Visibility tiers in the UI

Group view shows paid, pending or late status and the auction result. A member's amounts and risk details appear only in their private view. The organizer sees everything. Tier defaults are configurable per circle; the UI never reveals more than the viewer's tier even if the API returned it (defense in depth, but the API enforces first).

## 6. Internationalisation and localisation

- ICU message format with `next-intl` (web) and `i18next` or `expo-localization` (mobile); translations managed in a platform with review.
- `Intl.NumberFormat` for money, with currency from the circle, never from the device.
- Numbering systems, calendars and **right-to-left** layouts supported from the start (logical CSS properties).
- Time zones: display in the member's zone, but due dates are defined in the circle's zone.
- Plain-language mode and short, concrete wording; test with real community users.

## 7. Notifications UX

- Preference center per channel and event type, with quiet hours.
- Reminders escalate in tone, not in volume: friendly, then firm, then organizer-notified.
- Every message states the amount, the due date, and a one-tap pay link.
- Opt-out is always honoured and recorded.

## 8. Quality bar

- Lighthouse and Web Vitals budgets in CI for the web app.
- End-to-end tests with Playwright (web) and Maestro or Detox (mobile) on the critical paths: join, pay, bid, approve.
- Accessibility checks (axe) in CI; manual screen-reader pass each release.
