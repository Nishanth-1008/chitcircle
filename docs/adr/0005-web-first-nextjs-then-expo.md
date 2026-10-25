# ADR 0005: Web first with Next.js; mobile second with Expo

**Status:** Accepted

## Context
The product needs a website and a mobile app. The hero timeline uses Bryntum, which is a web component. The hackathon timeline is short. The team knows TypeScript and React.

## Decision
Ship the responsive Next.js app (installable as a PWA) first. Build the mobile app with Expo (React Native) after the core is hardened. Share a typed API client generated from FastAPI's OpenAPI spec, plus formatting helpers and design tokens, in a monorepo.

## Consequences
- One contract for both clients; CI fails on stale generated clients.
- Mobile reuses skills and code but needs a custom timeline grid.
- Native-only capabilities (push, biometrics, deep links) arrive in Phase 4.

## Alternatives considered
- **Flutter:** strong rendering and single codebase, but loses shared TypeScript and React knowledge.
- **Capacitor wrapper around the web app:** fastest to ship, weaker native feel; remains a fallback.
- **Native Swift and Kotlin:** highest quality, highest cost.

## Revisit when
Mobile performance or platform features demand native modules beyond what Expo supports.
