# Phase 4: Mobile App, Notifications and Live Auctions

**Timing:** about 6 to 8 weeks (can overlap with the end of Phase 3)
**Goal:** Meet members where they are: on their phones, with timely messages and live auctions.

## Workstreams

### A. Mobile app (Expo) (see `09`)
- [ ] Monorepo package for the generated API client; shared formatting and tokens
- [ ] Auth with phone OTP; secure token storage; biometric gate for approvals
- [ ] Screens: home, timeline (custom grid), pay, bid with effective-rate preview, settlement breakdown, approvals, ledger, settings
- [ ] Deep links from notifications and invites
- [ ] Offline read-only cache; no offline bids or approvals
- [ ] EAS Build, EAS Update, internal testing tracks, store submission
- [ ] Crash and performance monitoring

### B. Notifications (see `05` section 8)
- [ ] Preference center: channels, event types, quiet hours, language
- [ ] Channel adapters: push, email, SMS; message-app channel as opt-in premium
- [ ] Versioned templates per language; delivery log and status callbacks
- [ ] Fallback order per user; de-duplication
- [ ] Escalation tone ladder wired to the collections agent

### C. Live auctions
- [ ] Realtime gateway with SSE; Redis pub/sub fan-out
- [ ] Sealed and open modes in the UI; countdown from server time
- [ ] Optional anti-sniping extension as a ruleset flag
- [ ] Load test with realistic connection counts

### D. Web improvements
- [ ] PWA install and offline shell
- [ ] Accessibility audit and fixes (WCAG 2.1 AA target)
- [ ] Right-to-left layout and first additional languages
- [ ] Organizer onboarding wizard and circle templates

### E. Product analytics
- [ ] Funnel: invite accepted, first payment, first auction, first settlement
- [ ] Privacy-preserving analytics without amounts at user level

## Exit criteria

- Mobile app in both stores (or at least in testing tracks) with the core journeys passing end-to-end tests
- Push and email delivery above agreed success rates; opt-outs honoured
- Live auction with at least 200 concurrent viewers per circle in tests
- Accessibility audit completed with critical issues closed
- At least two additional languages shipped and reviewed by native speakers

## Risks

| Risk | Mitigation |
|---|---|
| App-store review delays | Use over-the-air updates for JS changes; plan review buffers |
| Message-app templates need approval and cost money | Start with push and email; add as premium |
| SMS abuse and cost | OTP rate limits, country allow-lists, fraud guards |
| Poor connectivity | Light payloads, ETags, optimistic non-financial UI, clear pending states |
