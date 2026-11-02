# ChitCircle Frontend-to-Backend Integration Specification & Wireframes

> **Target Audience:** Backend Engineers building, integrating, and testing FastAPI endpoints for the ChitCircle Next.js frontend.  
> **Status:** Production Reference & Contract Specification  
> **Frontend Stack:** Next.js 15 (App Router), TypeScript, Design Tokens (CSS), TanStack Query / custom hooks, Vitest.  
> **Backend Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL, Redis, Celery, PayPal Sandbox SDK.  
> **Financial Core Principle:** Money is ALWAYS strictly formatted as integer minor units (paise / cents) with an ISO currency code (e.g., `500000` INR = ₹5,000.00). **Never use floating point numbers.**

---

## Table of Contents

1. [Architecture & Communication Contract](#1-architecture--communication-contract)
   - [Next.js Reverse Proxy (`/api/backend/*`)](#nextjs-reverse-proxy)
   - [Authentication & Identity Headers](#authentication--identity-headers)
   - [Financial Numbers & Idempotency Rules](#financial-numbers--idempotency-rules)
2. [Master Screen & Button Inventory](#2-master-screen--button-inventory)
3. [Screen-by-Screen Wireframes & Button Specifications](#3-screen-by-screen-wireframes--button-specifications)
   - [3.1 Welcome & Public Onboarding (`/welcome`)](#31-welcome--public-onboarding-welcome)
   - [3.2 Development Sign-In (`/sign-in`)](#32-development-sign-in-sign-in)
   - [3.3 Global App Shell & Navigation (`AppShell`, `BottomNav`, `TopBar`)](#33-global-app-shell--navigation-appshell-bottomnav-topbar)
   - [3.4 Organizer / Member Dashboard (`/app/home`)](#34-organizer--member-dashboard-apphome)
   - [3.5 Circle Modal (`OpenCircleSheet`) — Open & Create](#35-circle-modal-opencirclesheet--open--create)
   - [3.6 Circles Directory (`/app/circles`)](#36-circles-directory-appcircles)
   - [3.7 Circle Detail Workspace (`/app/circles/[circleId]`)](#37-circle-detail-workspace-appcirclescircleid)
   - [3.8 Round / Cycle Execution Workspace (`/app/circles/[circleId]/cycles/[cycleId]`)](#38-round--cycle-execution-workspace-appcirclescircleidcyclescycleid)
   - [3.9 Activity & Shared Ledger (`/app/activity`)](#39-activity--shared-ledger-appactivity)
   - [3.10 Settlement & Payout Engine (`/app/settlements/[settlementId]`)](#310-settlement--payout-engine-appsettlementssettlementid)
   - [3.11 Reconciliation & Audit Inspector (`/app/settlements/[settlementId]/reconciliation`)](#311-reconciliation--audit-inspector-appsettlementssettlementidreconciliation)
   - [3.12 Profile & System Diagnostics (`/app/profile`)](#312-profile--system-diagnostics-appprofile)
   - [3.13 Help, FAQ & Capability Matrix (`/app/help`)](#313-help-faq--capability-matrix-apphelp)
   - [3.14 System Fallback Screens (`/error.tsx`, `/not-found.tsx`)](#314-system-fallback-screens-errortsx-not-foundtsx)
4. [Agent Mandates & Approvals Queue Integration](#4-agent-mandates--approvals-queue-integration)
5. [PayPal & Payment Webhooks Architecture](#5-paypal--payment-webhooks-architecture)
6. [Backend Engineer Integration Checklist](#6-backend-engineer-integration-checklist)

---

## 1. Architecture & Communication Contract

### Next.js Reverse Proxy

To eliminate CORS issues and protect backend server URLs from public exposure, the browser **never** calls the backend port directly. Instead, all browser requests are directed to the same-origin proxy `/api/backend/*`, which Next.js forwards to `CHITCIRCLE_API_URL` (configured via `next.config.mjs` and `.env.local`).

```
+--------------------------------+               +-------------------------------------+
|        Browser Client          |               |          Next.js Server             |
|                                |  HTTP Fetch   |  (Rewrites /api/backend/:path*)     |
|  Calls /api/backend/circles/1  +-------------->+  Proxies to CHITCIRCLE_API_URL      |
+--------------------------------+               +------------------+------------------+
                                                                    |
                                                                    | Internal HTTP
                                                                    v
                                                 +-------------------------------------+
                                                 |          FastAPI Backend            |
                                                 |        http://localhost:8000        |
                                                 |                                     |
                                                 |  Receives /circles/1                |
                                                 |  Processes & validates business rules|
                                                 +-------------------------------------+
```

> **IMPORTANT for Backend Developers:**  
> When you add new top-level backend routes (e.g. `/auth`, `/collections`, `/mandates`, `/ops`), you **must** ensure they are included in `frontend/next.config.mjs` under the `rewrites()` allow-list:
> ```js
> return ['health', 'circles', 'cycles', 'settlements', 'ledger', 'auth', 'collections', 'mandates', 'ops'].flatMap(...)
> ```

---

### Authentication & Identity Headers

The frontend operates in two distinct modes:

1. **Demo Mode (`mode: 'demo'`):**  
   Runs entirely against client-side deterministic fixtures (`src/lib/api/demo.ts`). No backend requests are dispatched.
2. **Live Mode (`mode: 'live'`):**  
   Every API request is made with the identity headers set in `src/lib/api/client.ts`:
   - `X-Actor-Id`: The user ID of the caller (e.g., `user_01H...` or `org_01H...`).
   - `X-Actor-Role`: The claimed role (`organizer`, `member`, or `approver`).
   - `Accept`: `application/json`
   - `Content-Type`: `application/json` (on `POST` / `PUT`)

#### Target Production Authentication:
The backend already supports OAuth2 password flow with JWT (`/auth/login` and `/auth/register`). When switching from dev stub headers to JWT:
- Frontend will store the Bearer token in `localStorage` or secure cookie.
- Requests will include header: `Authorization: Bearer <access_token>`.
- The backend `get_current_actor` dependency will decode `sub` and populate actor context.

---

### Financial Numbers & Idempotency Rules

1. **Integer Minor Units:**  
   Every monetary amount transmitted in request bodies or returned in responses is an **integer** representing the smallest currency denomination (e.g., `1000000` = ₹10,000.00). Floating point types in monetary calculations will be rejected.
2. **Idempotency & Double-Click Protection:**  
   - All state-mutating UI buttons are wrapped with `useSingleFlight` (synchronous in-flight ref locking). While a request is in flight, subsequent clicks are discarded and the button displays a loading spinner or label (`"Checking..."`, `"Creating..."`).
   - Sensitive financial operations (payment collections, payouts, settlements) must consume an idempotency key (e.g., `f"collection:{cycle.id}:{member_id}"`).

---

## 2. Master Screen & Button Inventory

Below is an exhaustive inventory of every interactive control, link, form, and button across the frontend application:

| # | Screen / Component | Element Label / Icon | Control Type | Target API Endpoint | HTTP Method | Guard / Role | Primary Action |
|---|---|---|---|---|---|---|---|
| 1 | `/welcome` | **Explore the demo** | `<Button>` | *None (Local)* | - | Guest | Activates demo session & redirects to `/app/home` |
| 2 | `/welcome` | **Sign in (development)** | `<LinkButton>` | *None (Nav)* | - | Guest | Navigates to `/sign-in` |
| 3 | `/welcome` | **Sign in isn’t available yet** | `<Button disabled>`| - | - | Guest | Disabled when `NEXT_PUBLIC_LIVE_API_ENABLED=false` |
| 4 | `/sign-in` | **Continue** | `<Button type="submit">`| `/auth/login` *(target)* | `POST` | Guest | Submits dev identity credentials / logs in |
| 5 | `/sign-in` | **Back** | `<Button variant="ghost">`| *None (Nav)* | - | Any | Returns to `/welcome` |
| 6 | `AppShell` / `BottomNav` | **Home** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/home` |
| 7 | `AppShell` / `BottomNav` | **Circles** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/circles` |
| 8 | `AppShell` / `BottomNav` | **Activity** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/activity` |
| 9 | `AppShell` / `BottomNav` | **Profile** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/profile` |
| 10 | `TopBar` | **Back (`chevronLeft`)** | `<Link>` | *None (Nav)* | - | Any | Returns to parent screen |
| 11 | `TopBar` | **Avatar (`Profile`)** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/profile` |
| 12 | `/app/home` | **Open a circle (Header)** | `<Button icon="plus">`| *None (Modal)* | - | Any | Opens `OpenCircleSheet` modal |
| 13 | `/app/home` | **My circles (Tile)** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/circles` |
| 14 | `/app/home` | **Activity (Tile)** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/activity` |
| 15 | `/app/home` | **Open a circle (Empty State)** | `<Button>` | *None (Modal)* | - | Any | Opens `OpenCircleSheet` modal |
| 16 | `/app/home` | **View this round (`DueCard`)** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/circles/{id}/cycles/{id}` |
| 17 | `/app/home` | **Action Item (Alert Card)** | `<Link>` | *None (Nav)* | - | Any | Navigates directly to cycle with active action |
| 18 | `/app/home` | **View all (`Your circles`)** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/circles` |
| 19 | `/app/home` | **Circle Card Item** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/circles/{circleId}` |
| 20 | `/app/home` | **See all (`Recent activity`)** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/activity` |
| 21 | `OpenCircleSheet` | **Open by ID (Tab)** | `<Button>` | *None (Local)* | - | Any | Switches to "Open by ID" tab |
| 22 | `OpenCircleSheet` | **Create New Circle (Tab)** | `<Button>` | *None (Local)* | - | Any | Switches to "Create New Circle" tab |
| 23 | `OpenCircleSheet` | **Open circle** | `<Button type="submit">`| `/circles/{id}` | `GET` | Any | Verifies circle on server, saves ID, navigates |
| 24 | `OpenCircleSheet` | **Create Circle on Server** | `<Button type="submit">`| `/circles` | `POST` | Organizer | Creates new circle with full ruleset & members |
| 25 | `/app/circles` | **Open (`+`)** | `<Button small>` | *None (Modal)* | - | Any | Opens `OpenCircleSheet` modal |
| 26 | `/app/circles` | **Active / Payments / Completed** | `<FilterTabs>` | *None (Filter)*| - | Any | Filters local circle list |
| 27 | `/app/circles` | **Remove from this device** | `<Button variant="ghost">`| *None (Local)* | - | Any | Deletes invalid circle from device memory |
| 28 | `/app/circles/[id]` | **Overview / Members / Rules / Rounds**| `<FilterTabs>` | *None (Filter)*| - | Any | Toggles circle view tabs |
| 29 | `/app/circles/[id]` | **Start Next Round** | `<Button>` | `/circles/{id}/cycles`| `POST` | Organizer | Creates & schedules next monthly cycle |
| 30 | `/app/circles/[id]` | **Open round** | `<Button type="submit">`| `/cycles/{id}` | `GET` | Any | Validates round ID and navigates to workspace |
| 31 | `/app/circles/[id]` | **Round Row Item** | `<Link>` | *None (Nav)* | - | Any | Navigates to round workspace |
| 32 | `/app/circles/[id]` | **Update Security (Target)** | `<Button>` | `/circles/{id}/members/{m}/security` | `PUT` | Organizer | Verifies collateral or guarantor |
| 33 | `/app/circles/[id]/cycles/[id]` | **Review settlement** | `<Link>` | *None (Nav)* | - | Any | Navigates to settlement view |
| 34 | `/app/circles/[id]/cycles/[id]` | **Activity (See all)** | `<Link>` | *None (Nav)* | - | Any | Opens `/app/activity?round={id}` |
| 35 | `/app/circles/[id]/cycles/[id]` | **Activity Row (Accordion)** | `<button>` | *None (Local)* | - | Any | Expands ledger entry to show journal postings |
| 36 | `/app/circles/[id]/cycles/[id]` | **Round history (Accordion)** | `<summary>` | *None (Local)* | - | Any | Toggles historical state transitions |
| 37 | `/app/circles/[id]/cycles/[id]` | **Start Collections (Action)** | `<Button>` | `/cycles/{id}/open` | `POST` | Organizer | Transitions cycle from DRAFT to OPEN |
| 38 | `/app/circles/[id]/cycles/[id]` | **Open Auction (Action)** | `<Button>` | `/cycles/{id}/auction/open` | `POST` | Organizer | Starts bidding period for cycle |
| 39 | `/app/circles/[id]/cycles/[id]` | **Submit Bid (Action)** | `<Button type="submit">`| `/cycles/{id}/auction/bids` | `POST` | Member | Submits sealed/open bid discount |
| 40 | `/app/circles/[id]/cycles/[id]` | **Close Auction (Action)** | `<Button>` | `/cycles/{id}/auction/close`| `POST` | Organizer | Closes bidding and determines winner |
| 41 | `/app/circles/[id]/cycles/[id]` | **Calculate Settlement (Action)**| `<Button>` | `/cycles/{id}/settlement` | `POST` | Organizer | Calculates net contributions & dividends |
| 42 | `/app/circles/[id]/cycles/[id]` | **Pay Contribution (PayPal)** | `<Button>` | `/collections/create` | `POST` | Member | Generates PayPal collection invoice / order |
| 43 | `/app/activity` | **Round Selectors** | `<button role="tab">`| *None (Local)* | - | Any | Switches displayed cycle ledger |
| 44 | `/app/activity` | **Activity Filter Tabs** | `<FilterTabs>` | *None (Filter)*| - | Any | Filters ledger by All, Incoming, Outgoing, Due |
| 45 | `/app/activity` | **Open Settlement (Link)** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/settlements/{id}` |
| 46 | `/app/settlements/[id]` | **Reconciliation (Card)** | `<Link>` | *None (Nav)* | - | Any | Navigates to reconciliation report |
| 47 | `/app/settlements/[id]` | **Approve Settlement (Action)** | `<Button>` | `/settlements/{id}/approvals` | `POST` | Approver | Submits approval decision with reason |
| 48 | `/app/settlements/[id]` | **Execute Payout (Action)** | `<Button>` | `/settlements/{id}/payout` | `POST` | Organizer | Initiates payout to winning member |
| 49 | `/app/settlements/[id]` | **Check Payout Status (Action)**| `<Button>` | `/settlements/{id}/payout/check` | `POST` | Organizer | Polls gateway status for pending payout |
| 50 | `/app/settlements/[id]` | **Finalize Round (Action)** | `<Button>` | `/settlements/{id}/finalize` | `POST` | Organizer | Closes cycle after reconciliation passes |
| 51 | `/app/settlements/[id]/reconciliation` | **Rerun Reconciliation** | `<Button>` | `/ops/reconciliation/rerun` | `POST` | Organizer | Re-triggers backend reconciliation worker |
| 52 | `/app/profile` | **Theme Switcher** | `<button>` (Segmented) | *None (Local)* | - | Any | Persists theme choice to `localStorage` |
| 53 | `/app/profile` | **Reset demo data** | `<Button variant="secondary">`| *None (Local)* | - | Demo | Resets demo circles to defaults |
| 54 | `/app/profile` | **Clear saved** | `<Button variant="secondary">`| *None (Local)* | - | Any | Flushes cached circle IDs on device |
| 55 | `/app/profile` | **Check API** | `<Button variant="secondary">`| `/health` | `GET` | Live | Pings backend health endpoint |
| 56 | `/app/profile` | **Help & what’s connected** | `<Link>` | *None (Nav)* | - | Any | Navigates to `/app/help` |
| 57 | `/app/profile` | **Sign out** | `<Button variant="secondary">`| *None (Auth)* | - | Any | Clears session context & redirects to `/welcome` |
| 58 | `/app/help` | **FAQ Accordions** | `<summary>` | *None (Local)* | - | Any | Expands and collapses FAQ answers |
| 59 | `ErrorState` / `error.tsx` | **Try again** | `<Button>` | *None (Retry)* | - | Any | Retries failed query fetcher / resets error boundary |
| 60 | `StaleNotice` | **Retry** | `<button className="link">` | *None (Retry)* | - | Any | Re-fetches resource when background refresh failed |

---

## 3. Screen-by-Screen Wireframes & Button Specifications

---

### 3.1 Welcome & Public Onboarding (`/welcome`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
|  [ChitCircle Logo]                                    |
|                                                       |
|  (calendar) Clear schedules                           |
|  (receipt)  Shared records                            |
|  (scale)    Open rules                                |
|                                                       |
|  Community savings, made simpler.                     |
|  Manage circles, contributions, and payouts in one    |
|  place.                                               |
|                                                       |
|  +-------------------------------------------------+  |
|  | [ Explore the demo ]               (Button #1)  |  |
|  +-------------------------------------------------+  |
|  | [ Sign in (development) ]          (Button #2)  |  |
|  +-------------------------------------------------+  |
|                                                       |
|  Account sign-up needs the authentication service,   |
|  which isn’t built yet. The demo uses fictional data. |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #1: "Explore the demo"
- **Location:** Welcome hero CTA stack.
- **Component:** `<Button block onClick={...}>` in `src/app/welcome/page.tsx`.
- **Condition:** Always active.
- **Client Action:** Calls `startDemo()` in `SessionProvider`. Sets `mode: 'demo'` and actor `{ id: 'demo-alex', role: 'member', displayName: 'Alex' }`. Redirects to `/app/home`.
- **Backend Connection:** None (demo mode).

##### Button #2: "Sign in (development)"
- **Location:** Secondary CTA stack.
- **Component:** `<Link href="/sign-in" className="btn btn--secondary btn--block">`.
- **Condition:** Rendered when `NEXT_PUBLIC_LIVE_API_ENABLED=true`. If false, renders disabled `<Button>` with label *"Sign in isn’t available yet"*.
- **Client Action:** Navigates client router to `/sign-in`.

---

### 3.2 Development Sign-In (`/sign-in`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
|  [ChitCircle Logo]                                    |
|  Development sign-in                                  |
|  [!] Not real authentication. Backend trusts ID & role|
|                                                       |
|  Actor ID:                                            |
|  [ org_01H89XYZ...                                  ] |
|  For members this is member ID; for organizers it is  |
|  the organizer ID.                                    |
|                                                       |
|  Header role:                                         |
|  [ organizer v ]  (member / organizer / approver)     |
|  Sent as X-Actor-Role. Server enforces permissions.   |
|                                                       |
|  +-------------------------------------------------+  |
|  | [ Continue ]                       (Button #4)  |  |
|  +-------------------------------------------------+  |
|  | [ Back ]                           (Button #5)  |  |
|  +-------------------------------------------------+  |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #4: "Continue" (Sign-In Submit)
- **Location:** Main form action in `src/app/sign-in/page.tsx`.
- **Component:** `<Button block type="submit" disabled={!liveAvailable}>`.
- **Permissions:** Any guest.
- **Validation:** Requires non-empty trimmed `actorId`. Displays inline error if empty.
- **Current Behavior:** Calls `signInDev(actorId, role)`, setting `mode: 'live'` and actor details in local session state, then routes to `/app/home`.
- **Target Backend Integration (Production OAuth2 / JWT):**
  - **Endpoint:** `POST /auth/login`
  - **Content-Type:** `application/x-www-form-urlencoded`
  - **Request Body:**
    ```
    username=organizer@example.com&password=secretpassword123
    ```
  - **Success Response (200 OK):**
    ```json
    {
      "access_token": "eyJhbGciOi...",
      "token_type": "bearer",
      "user_id": "usr_9901",
      "role": "organizer"
    }
    ```
  - **Error Responses:**
    - `401 Unauthorized`: `{"detail": "Incorrect email or password"}`
    - `400 Bad Request`: `{"detail": "Inactive user"}`
  - **Client UI Feedback:** Displays error message in `field__error` span; sets JWT token in session upon success.

##### Button #5: "Back"
- **Location:** Secondary form action.
- **Component:** `<Button block variant="ghost" onClick={() => router.push('/welcome')}>`.
- **Client Action:** Navigates back to `/welcome`.

---

### 3.3 Global App Shell & Navigation (`AppShell`, `BottomNav`, `TopBar`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| [< Back]             [ChitCircle]            [(Avatar)|
+-------------------------------------------------------+
|                                                       |
|                    Screen Content                     |
|                                                       |
+-------------------------------------------------------+
|   (home)        (circles)       (activity)   (profile)|
|    Home          Circles         Activity     Profile |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### TopBar Navigation
- **Button #10: Back Button (`<Link className="topbar__back">`):**  
  Visible when `back` prop is supplied. Navigates to designated parent route.
- **Button #11: Avatar Button (`<Link href="/app/profile">`):**  
  Displays user initials. Navigates to `/app/profile`.

##### BottomNav Navigation
- **Buttons #6 - #9: Tab Links (`Home`, `Circles`, `Activity`, `Profile`):**  
  Active route gets `aria-current="page"` and highlighted brand styling. Persistent on all authenticated screens.

---

### 3.4 Organizer / Member Dashboard (`/app/home`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| ChitCircle                                       (Av) |
| Good morning, Alex                                    |
| 2 circles saved on this device                        |
|                                                       |
| +---------------------------------------------------+ |
| | [+] Open a circle                    (Button #12) | |
| +---------------------------------------------------+ |
|                                                       |
| [ (circles) My circles ]      [ (activity) Activity ] |
|                                                       |
| +--- DUE SOON CARD ---------------------------------+ |
| | (clock) Due 15 Nov · in 13 days                   | |
| | ₹10,000                                           | |
| | Tech Colleagues Circle · Round 2                  | |
| | Online payment isn’t connected yet.               | |
| | [ View this round -> ]               (Button #16) | |
| +---------------------------------------------------+ |
|                                                       |
| +--- NEEDS YOUR ATTENTION --------------------------+ |
| | (!) Auction is open                               | |
| |     Weekend Family Chit #4 · Round 1          [>] | |
| +---------------------------------------------------+ |
|                                                       |
| YOUR CIRCLES                             [ View all ] |
| +--- FEATURED CIRCLE CARD --------------------------+ |
| | Weekend Family Chit #4       [ Awaiting approval ]| |
| | 20 members · Round 1                              | |
| | Next due: 10 Nov | Your balance: ₹0 | Role: Org   | |
| | Contributions settled: [=======---] 18 of 20      | |
| +---------------------------------------------------+ |
|                                                       |
| RECENT ACTIVITY                          [ See all ]  |
| - Contribution received · Neha · 10:30 AM   +₹5,000   |
| - Contribution received · Rahul · 09:15 AM  +₹5,000   |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #12: "Open a circle"
- **Location:** Primary action button below greeting.
- **Component:** `<Button block icon="plus" onClick={() => setSheet(true)}>`.
- **Client Action:** Sets `sheet = true`, opening the `OpenCircleSheet` bottom sheet modal.

##### Button #13 & #14: Quick Action Tiles ("My circles" & "Activity")
- **Component:** `<Link href="/app/circles" className="tile">` & `<Link href="/app/activity" className="tile">`.
- **Client Action:** Client navigation.

##### Button #16: "View this round" (`DueCard`)
- **Location:** Footer of the outstanding obligation banner.
- **Component:** `<Link href={`/app/circles/${circleId}/cycles/${round.id}`} className="link">`.
- **Backend Linkage:** Directly opens the active round workspace.

##### Button #17: Needs Attention Alert Items
- **Location:** Attention list items generated by `actionItems()`.
- **Triggers:**
  - Round in `AUCTION_OPEN` -> Navigates to round to place bid or view auction.
  - Round in `AWAITING_APPROVAL` (and user is organizer) -> Navigates to round for approval.
  - Round in `ON_HOLD`, `FAILED`, or `DISPUTED` -> Navigates to exception resolution.

##### Button #18 & #20: Section Links ("View all" & "See all")
- **Target:** Navigates to `/app/circles` and `/app/activity` respectively.

---

### 3.5 Circle Modal (`OpenCircleSheet`) — Open & Create

#### ASCII Wireframe
```
+-------------------------------------------------------+
|  [===] (Grab handle)                                  |
|  Open a circle / Create a circle                      |
|                                                       |
|  [ Open by ID ]          [ Create New Circle ]        |
|                                                       |
|  === IF "OPEN BY ID" TAB SELECTED ===                 |
|  Circle ID:                                           |
|  [ crcl_01H89ABC...                                 ] |
|  Circles you open are remembered on this device only. |
|  +-------------------------------------------------+  |
|  | [ Open circle ]                     (Button #23)|  |
|  +-------------------------------------------------+  |
|                                                       |
|  === IF "CREATE NEW CIRCLE" TAB SELECTED ===          |
|  Circle Name:                                         |
|  [ Family Savings Circle #1                         ] |
|  Total Chit Pool (INR):                               |
|  [ 100000                                           ] |
|  Members (comma-separated IDs/names):                 |
|  [ Alice, Bob, Charlie                              ] |
|  +-------------------------------------------------+  |
|  | [ Create Circle on Server ]         (Button #24)|  |
|  +-------------------------------------------------+  |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #23: "Open circle" (Form Submission)
- **Location:** "Open by ID" tab in `src/components/OpenCircleSheet.tsx`.
- **Component:** `<Button block type="submit" disabled={openAction.pending}>`.
- **Double-Click Guard:** Handled by `useSingleFlight`. Label toggles to `"Checking…"`.
- **Backend Request:**
  - **Endpoint:** `GET /circles/{circle_id}`
  - **Headers:** `X-Actor-Id`, `X-Actor-Role`, `Accept: application/json`
  - **URL Parameter:** `circle_id` (string, URL-encoded)
- **Backend Response Handling:**
  - **200 OK:**
    ```json
    {
      "id": "crcl_01H89XYZ",
      "name": "Weekend Family Chit #4",
      "organizer_id": "usr_organizer_01",
      "members": [
        {"id": "usr_01", "name": "Alice", "position": 1, "has_won": false, "security_status": "VERIFIED"},
        {"id": "usr_02", "name": "Bob", "position": 2, "has_won": false, "security_status": "NONE"}
      ],
      "rulesets": [
        {"version": 1, "status": "ACTIVE", "fingerprint": "a3f5c7...", "reason": "Initial setup"}
      ]
    }
    ```
    *Frontend Action:* Saves circle ID in `localStorage` via `saved.saveCircle(circle.id)`, closes sheet modal, clears form input, and routes to `/app/circles/crcl_01H89XYZ`.
  - **404 Not Found:**
    ```json
    {"detail": "Circle not found"}
    ```
    *Frontend Action:* Displays error message in `field__error`: *"Circle not found"*. Keeps sheet open.
  - **401 / 403 Forbidden:**
    ```json
    {"detail": "You do not have permission to view this circle"}
    ```
    *Frontend Action:* Displays permission error; input is highlighted in danger tone.

##### Button #24: "Create Circle on Server" (Form Submission)
- **Location:** "Create New Circle" tab in `src/components/OpenCircleSheet.tsx`.
- **Component:** `<Button block type="submit" disabled={createAction.pending}>`.
- **Double-Click Guard:** Handled by `useSingleFlight`. Label toggles to `"Creating…"`.
- **Precondition:** Only executable when `ctx.mode === 'live'` and user is authorized.
- **Backend Request:**
  - **Endpoint:** `POST /circles`
  - **Headers:** `X-Actor-Id: <actor_id>`, `X-Actor-Role: organizer`, `Content-Type: application/json`
  - **Request Body (`schemas.CreateCircle`):**
    ```json
    {
      "name": "Family Savings Circle #1",
      "ruleset": {
        "currency": "INR",
        "total_chit_value": 10000000,
        "member_count": 4,
        "payout_mode": "SEALED_BID_AUCTION",
        "commission": {
          "base": "PERCENT_OF_CHIT_VALUE",
          "rate": "0.05",
          "rounding": "HALF_UP"
        },
        "dividend": {
          "allocation": "ALL_MEMBERS"
        },
        "auction": {
          "max_discount_rate": "0.40",
          "min_discount": 0,
          "increment": 0,
          "tie_break": "EARLIEST_BID",
          "no_bid_fallback": "HOLD"
        },
        "grace_period_days": 5,
        "rounding": {
          "contribution_remainder": "REJECT",
          "remainder_destination": null
        },
        "required_approvals": 1,
        "require_security": false,
        "jurisdiction_profile": "IN-SANDBOX",
        "effective_date": "2026-11-02",
        "status": "ACTIVE"
      },
      "members": ["usr_organizer", "Alice", "Bob", "Charlie"]
    }
    ```
    *Note: `total_chit_value` is sent in integer minor units (₹100,000 * 100 = 10000000).*
- **Backend Response Handling:**
  - **201 Created:**
    ```json
    {
      "id": "crcl_new_9912",
      "name": "Family Savings Circle #1",
      "organizer_id": "usr_organizer",
      "ruleset_version": 1,
      "members": [
        {"id": "usr_organizer", "name": "usr_organizer", "position": 1},
        {"id": "usr_m2", "name": "Alice", "position": 2},
        {"id": "usr_m3", "name": "Bob", "position": 3},
        {"id": "usr_m4", "name": "Charlie", "position": 4}
      ]
    }
    ```
    *Frontend Action:* Saves new circle ID to device, closes sheet, resets fields, and routes to `/app/circles/crcl_new_9912`.
  - **400 Bad Request / 422 Unprocessable Entity:**
    Displays backend validation error detail in a red danger banner above the submit button.

---

### 3.6 Circles Directory (`/app/circles`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| My circles                                      [+]   |
|                                                       |
| [ Active (2) ]     [ Payments ]        [ Completed ]  |
|                                                       |
| +--- CIRCLE CARD 1 ---------------------------------+ |
| | Weekend Family Chit #4       [ Awaiting approval ]| |
| | 20 members · Round 1                              | |
| | Next due: 10 Nov  | Your balance: ₹0  | Org       | |
| | Contributions: [========--] 18 of 20 settled      | |
| +---------------------------------------------------+ |
|                                                       |
| +--- CIRCLE CARD 2 ---------------------------------+ |
| | Tech Colleagues Circle              [ Collecting ]| |
| | 12 members · Round 2                              | |
| | Next due: 15 Nov  | Your balance: ₹10,000 | Mem   | |
| | Contributions: [=====-----] 6 of 12 settled       | |
| +---------------------------------------------------+ |
|                                                       |
| (i) Showing circles saved on this device.             |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #25: TopBar "Open" (`+`)
- **Location:** Header right slot.
- **Component:** `<Button small icon="plus" onClick={() => setSheet(true)}>Open</Button>`.
- **Action:** Opens `OpenCircleSheet`.

##### Button #26: Filter Tabs (`FilterTabs`)
- **Tabs:**
  - `Active`: Shows circles whose latest round is not in `FINALIZED` state.
  - `Payments`: Filters circles where `myObligation(round, actor).outstanding > 0`.
  - `Completed`: Shows circles where the latest saved round is `FINALIZED`.
- **Client Action:** Client-side predicate filter over `useOverviews` cached data.

##### Button #27: "Remove from this device" (Error Card Action)
- **Location:** Rendered if a saved circle ID fails to load from the server (e.g. 404 or revoked permission).
- **Component:** `<Button variant="ghost" small onClick={() => saved.forgetCircle(it.circleId)}>`.
- **Action:** Removes the orphaned ID from `localStorage`.

---

### 3.7 Circle Detail Workspace (`/app/circles/[circleId]`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| [<] Weekend Family Chit #4                            |
| [ You organize this circle ]                          |
|                                                       |
| [ Overview ]   [ Members ]   [ Rules ]   [ Rounds ]   |
|                                                       |
| === IF "OVERVIEW" SELECTED ===                        |
| Members: 20           | Payouts received: 0 of 20     |
| Active rule: v1       | Rounds on device: 1           |
|                                                       |
| +--- ORGANIZER ACTION: START NEXT ROUND ------------+ |
| | Start next round                                  | |
| | Create and schedule next monthly cycle on server. | |
| | [ Start Next Round ]                 (Button #29) | |
| +---------------------------------------------------+ |
|                                                       |
| +--- OPEN A ROUND ----------------------------------+ |
| | Round ID: [ cycl_01H...                         ] | |
| | [ Open round ]                       (Button #30) | |
| +---------------------------------------------------+ |
|                                                       |
| === IF "MEMBERS" SELECTED ===                         |
| (Av) Alice (you)        Position 1   [ Verified ]     |
| (Av) Bob                Position 2   [ Pending  ]     |
| (Av) Charlie            Position 3   [ None     ]     |
|                                                       |
| === IF "RULES" SELECTED ===                           |
| Version 1 [ Active ]                                  |
| Fingerprint: a3f5c7198a...                            |
| Reason: Initial setup                                 |
|                                                       |
| === IF "ROUNDS" SELECTED ===                          |
| - Round 1 · Due 10 Nov         [ Awaiting approval ]> |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #29: "Start Next Round"
- **Location:** "Overview" tab; rendered **only** when `role === 'organizer'` and `mode === 'live'`.
- **Component:** `<Button variant="primary" disabled={createCycleAction.pending}>`.
- **Double-Click Guard:** Handled by `useSingleFlight`. Label flips to `"Creating…"`.
- **Backend Request:**
  - **Endpoint:** `POST /circles/{circle_id}/cycles`
  - **Headers:** `X-Actor-Id: <actor_id>`, `X-Actor-Role: organizer`, `Content-Type: application/json`
  - **URL Parameter:** `circle_id` (string)
  - **Request Body (`schemas.NewCycle`):**
    ```json
    {
      "due_date": "2026-12-02T12:00:00.000Z",
      "ruleset_version": null
    }
    ```
    *If `ruleset_version` is null, the backend binds the circle's current active ruleset version.*
- **Backend Response Handling:**
  - **201 Created (`types.CycleView`):**
    ```json
    {
      "id": "cycl_02NOV99",
      "circle_id": "crcl_01H89XYZ",
      "number": 2,
      "ruleset_version": 1,
      "state": "DRAFT",
      "prior_state": null,
      "due_date": "2026-12-02T12:00:00Z",
      "payout_method": "SEALED_BID_AUCTION",
      "winner_member_id": null,
      "discount": null,
      "obligations": []
    }
    ```
    *Frontend Action:* Saves `res.id` to device storage and immediately redirects to `/app/circles/{circle_id}/cycles/{res.id}`.
  - **400 Bad Request / 409 Conflict:**
    Displays error: *"Previous cycle has not completed"* or *"Cycle already exists for date"*.

##### Button #30: "Open round" (Form Submission)
- **Location:** "Overview" tab form.
- **Component:** `<Button type="submit" block variant="secondary" disabled={open.pending}>`.
- **Double-Click Guard:** Handled by `useSingleFlight`.
- **Backend Request:**
  - **Endpoint:** `GET /cycles/{cycle_id}`
  - **Response Validation:** Validates that `cycle.circle_id === currentCircleId`. If it matches, saves to device and redirects to `/app/circles/{circleId}/cycles/{cycleId}`. Otherwise displays: *"That round belongs to a different circle."*

##### Button #32: Update Member Security (Organizer Action)
- **Location:** "Members" tab.
- **Backend Request:**
  - **Endpoint:** `PUT /circles/{circle_id}/members/{member_id}/security`
  - **Request Body (`schemas.SecurityIn`):**
    ```json
    {
      "status": "VERIFIED"
    }
    ```
    *Allowed statuses: `NONE`, `PENDING`, `VERIFIED`, `INVALID`.*
- **Backend Response (200 OK):**
  Updates `member.security_status`. Payout release remains blocked until winner's security status is `VERIFIED`.

---

### 3.8 Round / Cycle Execution Workspace (`/app/circles/[circleId]/cycles/[cycleId]`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| [<] Round 1                                           |
| Weekend Family Chit #4           [ Awaiting approval ]|
| Due 10 Nov · in 8 days                                |
|                                                       |
| [1.Collect] > [2.Recipient] > [3.Settlement] >        |
| [4.Approval*] > [5.Payout] > [6.Reconcile] > [7.Done] |
| Waiting for required approvals. Nothing paid out yet. |
|                                                       |
| +--- YOUR CONTRIBUTION -----------------------------+ |
| | Your contribution                    [ Settled ]  | |
| | Net due: ₹4,650 | Confirmed: ₹4,650 | Due: ₹0     | |
| +---------------------------------------------------+ |
|                                                       |
| +--- RECIPIENT THIS ROUND --------------------------+ |
| | (trophy) Lakshmi Devi                               | |
| | Winning discount: ₹12,000                           | |
| +---------------------------------------------------+ |
|                                                       |
| +--- REVIEW SETTLEMENT LINK ------------------------+ |
| | (scale) Review settlement                       [>] | |
| | Awaiting approval                                 | |
| +---------------------------------------------------+ |
|                                                       |
| +--- AUCTION BIDS (3 bids) -------------------------+ |
| | (Av) Lakshmi Devi                      ₹12,000      | |
| | (Av) Suresh Kumar                      ₹10,500      | |
| | (Av) Ramesh Patel                      [ Sealed ]   | |
| +---------------------------------------------------+ |
|                                                       |
| +--- CONTRIBUTIONS (20 members) --------------------+ |
| | (Av) Lakshmi Devi                    [ Settled ]    | |
| | (Av) Neha Gupta      ₹4,650 due      [ Outstanding] | |
| +---------------------------------------------------+ |
|                                                       |
| RECENT ACTIVITY                          [ See all ]  |
| - Dividend credited · Lakshmi · ₹350                  |
| - Commission allocated · Organizer · ₹5,000           |
|                                                       |
| > Round history (3 transitions)                       |
+-------------------------------------------------------+
```

#### Detailed Button & Write-Path Specifications

This workspace orchestrates the financial lifecycle of a cycle. Below are the state-specific buttons and their backend endpoints:

```
Cycle Lifecycle State Machine:
[DRAFT]
   │
   ▼  (POST /cycles/{id}/open)
[OPEN / COLLECTIONS_IN_PROGRESS]
   │
   ▼  (POST /cycles/{id}/auction/open)
[AUCTION_OPEN]
   │  ◄── (POST /cycles/{id}/auction/bids)
   ▼  (POST /cycles/{id}/auction/close)
[AUCTION_CLOSED]
   │
   ▼  (POST /cycles/{id}/recipient OR POST /cycles/{id}/settlement)
[SETTLEMENT_CALCULATED]
   │
   ▼  (POST /settlements/{id}/approvals -> APPROVE)
[APPROVED]
   │
   ▼  (POST /settlements/{id}/payout)
[PAYOUT_PENDING / PAYOUT_SUBMITTED]
   │  ◄── (POST /webhooks/provider OR /settlements/{id}/payout/check)
[PAYOUT_CONFIRMED]
   │
   ▼  (POST /settlements/{id}/reconciliation)
[RECONCILIATION_PENDING]
   │
   ▼  (POST /settlements/{id}/finalize)
[FINALIZED]
```

##### Button #37: "Open Cycle / Start Collections"
- **State Trigger:** When cycle is in `DRAFT`.
- **Role:** Organizer only.
- **Backend Request:** `POST /cycles/{cycle_id}/open`
- **Request Body:** None.
- **Backend Behavior:**
  - Validates circle ruleset.
  - Generates member obligations (`Obligation` rows) with `gross_due = chit_value / member_count`.
  - Writes ledger events: `CONTRIBUTION_DUE` for every member.
  - Advances cycle state: `DRAFT -> OPEN -> COLLECTIONS_IN_PROGRESS`.
- **Response (200 OK):** Returns updated `CycleView`.

##### Button #38: "Open Auction"
- **State Trigger:** When cycle is in `COLLECTIONS_IN_PROGRESS` or scheduled auction time arrives.
- **Role:** Organizer only.
- **Backend Request:** `POST /cycles/{cycle_id}/auction/open`
- **Backend Behavior:** Advances state to `AUCTION_OPEN`. Opens the bidding window.

##### Button #39: "Submit Bid"
- **State Trigger:** When cycle is in `AUCTION_OPEN`.
- **Role:** Eligible member who has not yet received a payout and is not in arrears.
- **Backend Request:**
  - **Endpoint:** `POST /cycles/{cycle_id}/auction/bids`
  - **Request Body (`schemas.BidIn`):**
    ```json
    {
      "member_id": "usr_alex_01",
      "discount": 1200000
    }
    ```
    *(Note: `discount` in minor units. E.g., ₹12,000 = `1200000`).*
- **Backend Validation:**
  - Ensures auction state is `AUCTION_OPEN`.
  - Verifies member has not won prior pot (`has_won == False`).
  - Verifies member has no overdue contributions beyond grace period.
  - Verifies discount is within cap (`discount <= total_chit_value * max_discount_rate`).
- **Response (200 OK):**
  ```json
  {
    "bid_id": "bid_018a7c",
    "member_id": "usr_alex_01",
    "accepted": true,
    "discount": null,
    "sealed": true
  }
  ```
  *(Sealed bids mask the discount amount until close).*

##### Button #40: "Close Auction"
- **State Trigger:** When bidding deadline is reached in `AUCTION_OPEN`.
- **Role:** Organizer only.
- **Backend Request:** `POST /cycles/{cycle_id}/auction/close`
- **Backend Behavior:**
  - Unseals bids.
  - Evaluates highest valid discount.
  - Applies tie-break rule (`EARLIEST_BID` or `RANDOM_DRAW`).
  - If no bids, executes configured fallback (`HOLD` or `LOTTERY`).
  - Sets `cycle.winner_member_id` and `cycle.discount`.
  - Advances state to `AUCTION_CLOSED`.

##### Button #41: "Calculate Settlement"
- **State Trigger:** When auction is closed and recipient is determined.
- **Role:** Organizer only.
- **Backend Request:** `POST /cycles/{cycle_id}/settlement`
- **Backend Behavior:**
  - Pure calculation engine (`financial_engine/settlement.py`).
  - Reconciles:
    $$\text{Winner Payout} = \text{Chit Value} - \text{Discount}$$
    $$\text{Dividend Pool} = \text{Discount} - \text{Commission}$$
    $$\text{Per-Member Dividend} = \lfloor \text{Dividend Pool} / N \rfloor$$
    $$\text{Net Contribution} = \text{Regular Installment} - \text{Dividend}$$
  - Creates persistent `Settlement` record.
  - Advances state to `SETTLEMENT_CALCULATED -> AWAITING_APPROVAL`.
- **Response (201 Created):** Returns full `SettlementView`.

##### Button #42: "Pay Contribution" (PayPal Integration)
- **State Trigger:** When member has outstanding obligation (`mine.outstanding > 0`).
- **Role:** Member.
- **Backend Request:**
  - **Endpoint:** `POST /collections/create`
  - **Query Params:** `cycle_id={cycle_id}&member_id={member_id}`
  - **Backend Behavior:**  
    Initializes PayPal Orders/Invoicing API. Generates payment URL with idempotency key `collection:{cycle_id}:{member_id}`.
  - **Response (200 OK):**
    ```json
    {
      "status": "CREATED",
      "invoice_id": "INV2-XYZ-123",
      "payment_url": "https://www.sandbox.paypal.com/checkoutnow?token=EC-9901"
    }
    ```
  - **Frontend Action:** Redirects browser to PayPal sandbox checkout.

---

### 3.9 Activity & Shared Ledger (`/app/activity`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| Activity                                              |
| (i) Activity is shown one round at a time.            |
|                                                       |
| [ Weekend Chit · R1 ]      [ Tech Circle · R2 ]       |
|                                                       |
| [ All ]    [ Incoming ]    [ Outgoing ]    [ Due ]    |
|                                                       |
| +--- LEDGER ENTRIES --------------------------------+ |
| | (v) Contribution received                  +₹4,650  |
| |     Lakshmi Devi · Today, 10:45 AM       [ Settled ]|
| |     [Click to expand journal postings]              |
| |     +-- Postings: --------------------------------+ |
| |     | Account                     Debit    Credit | |
| |     | member:usr_lakshmi:cleared  ₹4,650        - | |
| |     | circle:crcl_01:pool              -   ₹4,650 | |
| |     +---------------------------------------------+ |
| |     Event ID: ev_01H... | Actor: provider_webhook   | |
| |     Provider Ref: PAYID-MNB12345                    | |
| |                                                     |
| | (x) Contribution due                       -₹5,000  |
| |     Neha Gupta · 01 Nov, 00:00 AM      [ Due soon ] |
| +---------------------------------------------------+ |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #43: Round Selector Tabs
- **Component:** `<button role="tab" className="tab">`.
- **Client Action:** Switches selected cycle ID (`selectedId`). Triggers query:
  - **Endpoint:** `GET /cycles/{cycle_id}/ledger?limit=50`
  - **Response (200 OK):** List of `LedgerEventView` objects.

##### Button #44: Activity Filter Tabs
- **Filters:**
  - `All`: Complete chronological stream.
  - `Incoming`: `PAYMENT_CONFIRMED`, `DIVIDEND_CREDITED`.
  - `Outgoing`: `PAYOUT_CONFIRMED`, `REFUND_CONFIRMED`, `COMMISSION_ALLOCATED`.
  - `Due`: `CONTRIBUTION_DUE` (scheduled obligations).

##### Button #35: Activity Row Accordion Toggle
- **Component:** `<button type="button" className="activity__btn" onClick={onToggle}>`.
- **Client Action:** Expands the double-entry bookkeeping ledger details:
  - Displays journal postings table (`Account`, `Debit`, `Credit`).
  - Displays immutable Event ID, actor identity, rule version, provider reference, and reverses ID (if an adjustment).

##### Button #45: Settlement Deep Link
- **Location:** Inside expanded activity row where `settlement_id` is present.
- **Component:** `<Link href={`/app/settlements/${settlement_id}`}>Open settlement</Link>`.
- **Client Action:** Navigates directly to `/app/settlements/{settlementId}`.

---

### 3.10 Settlement & Payout Engine (`/app/settlements/[settlementId]`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| [<] Settlement                                        |
| Weekend Family Chit #4           [ Awaiting approval ]|
| Round 1                                               |
|                                                       |
| +--- SETTLEMENT BREAKDOWN --------------------------+ |
| | Gross chit value                       ₹100,000.00  |
| | Winning discount ( Lakshmi Devi )      -₹12,000.00  |
| | Winner payout                           ₹88,000.00  |
| | Organizer commission                     ₹5,000.00  |
| | Dividend pool                            ₹7,000.00  |
| | Rounding adjustment                          ₹0.00  |
| +---------------------------------------------------+ |
|                                                       |
| +--- YOUR NET CONTRIBUTION -------------------------+ |
| | ₹4,650.00                                         | |
| | After your dividend credit of ₹350.00               | |
| +---------------------------------------------------+ |
|                                                       |
| +--- PAYOUT DETAILS --------------------------------+ |
| | Requested: Not requested yet                        | |
| | Provider ref: None yet                              | |
| | Finalized: Not finalized                            | |
| | Payout key: payout:cycl_01H...:usr_lakshmi          | |
| +---------------------------------------------------+ |
|                                                       |
| +--- RECONCILIATION SUMMARY ------------------------+ |
| | (scale) Reconciliation                          [>] | |
| | Not yet reconciled — see what’s open                | |
| +---------------------------------------------------+ |
|                                                       |
| +--- WRITE ACTIONS (ORGANIZER / APPROVER) ----------+ |
| | [ Approve Settlement ]                 (Button #47) | |
| | [ Execute Payout via PayPal ]          (Button #48) | |
| | [ Finalize Round ]                     (Button #50) | |
| +---------------------------------------------------+ |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #47: "Approve Settlement"
- **Location:** Action panel on `/app/settlements/[settlementId]`.
- **Role:** Approver / Organizer.
- **Backend Request:**
  - **Endpoint:** `POST /settlements/{settlement_id}/approvals`
  - **Headers:** `X-Actor-Id: <id>`, `X-Actor-Role: approver`, `Content-Type: application/json`
  - **Request Body (`schemas.ApprovalIn`):**
    ```json
    {
      "decision": "APPROVE",
      "reason": "All 20 member contributions confirmed; collateral verified."
    }
    ```
- **Backend Behavior:**
  - Verifies caller has approval authority.
  - Increments approval count.
  - If required approvals met, transitions cycle state to `APPROVED`.
- **Response (200 OK):**
  ```json
  {"status": "APPROVED"}
  ```

##### Button #48: "Execute Payout"
- **Location:** Action panel; active only when status is `APPROVED`.
- **Role:** Organizer.
- **Backend Request:**
  - **Endpoint:** `POST /settlements/{settlement_id}/payout`
  - **Headers:** `X-Actor-Id: <id>`, `X-Actor-Role: organizer`
- **Backend Behavior:**
  - Checks if winner security status is `VERIFIED`. If `NONE` or `PENDING`, request fails with `403 Forbidden: Security check required before payout release`.
  - Dispatches call to PayPal Payouts API (`payout_gateway.create_payout`).
  - Records `PAYOUT_REQUESTED` in append-only ledger.
  - Sets `cycle.state = PAYOUT_PENDING` -> `PAYOUT_SUBMITTED`.
- **Response (200 OK):**
  ```json
  {
    "status": "SUBMITTED",
    "payout_reference": "payout:cycl_01:usr_lakshmi",
    "provider_payout_ref": "5UY90812XZ"
  }
  ```

##### Button #49: "Check Payout Status"
- **Location:** Rendered when payout status is `PAYOUT_SUBMITTED`.
- **Backend Request:** `POST /settlements/{settlement_id}/payout/check`
- **Backend Behavior:** Queries PayPal gateway for transfer confirmation. When confirmed, writes `PAYOUT_CONFIRMED` to ledger and advances state to `PAYOUT_CONFIRMED -> RECONCILIATION_PENDING`.

##### Button #50: "Finalize Round"
- **Location:** Rendered when state is `RECONCILIATION_PENDING`.
- **Backend Request:** `POST /settlements/{settlement_id}/finalize`
- **Backend Behavior:**
  - Runs full 3-way reconciliation audit (Obligations vs Payments, Payouts vs Clearing, Double-Entry Balance).
  - If clean (`is_clean == True`), writes `SETTLEMENT_FINALIZED` to ledger.
  - Updates winner record: sets `member.has_won = True`.
  - Sets `cycle.state = FINALIZED`.
- **Response (200 OK):**
  ```json
  {"status": "FINALIZED"}
  ```

---

### 3.11 Reconciliation & Audit Inspector (`/app/settlements/[settlementId]/reconciliation`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| [<] Reconciliation                                    |
| [!] Reconciliation required                           |
| Something doesn’t line up yet. A round can be         |
| finalized only when everything below is clear.        |
|                                                       |
| +--- MEMBER PAYMENTS -------------------------------+ |
| | Member payments                     [ Waiting ]   | |
| | Some provider payments are still pending.         | |
| | (!) Paid less than amount due                     | |
| |     Neha Gupta · Shortfall ₹1,000                   | |
| +---------------------------------------------------+ |
|                                                       |
| +--- WINNER PAYOUT ---------------------------------+ |
| | Winner payout                       [ Waiting ]   | |
| | No provider-confirmed payout yet.                 | |
| +---------------------------------------------------+ |
|                                                       |
| +--- LEDGER CHECKS ---------------------------------+ |
| | Ledger checks                       [ Balanced ]  | |
| | All journals balance and pool nets to zero.       | |
| +---------------------------------------------------+ |
|                                                       |
| +---------------------------------------------------+ |
| | [ Rerun Reconciliation Audit ]        (Button #51)| |
| +---------------------------------------------------+ |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #51: "Rerun Reconciliation Audit"
- **Location:** Action panel on `/app/settlements/[settlementId]/reconciliation`.
- **Backend Request:**
  - **Endpoint:** `POST /ops/reconciliation/rerun`
  - **Role:** Organizer / Ops.
  - **Backend Action:** Queues a Celery reconciliation background task (`provider_reconciliation`).
  - **Response (200 OK):**
    ```json
    {"job_id": 402, "status": "PENDING", "type": "provider_reconciliation"}
    ```
  - **Client UI Action:** Re-queries `GET /settlements/{settlement_id}/reconciliation` after 2 seconds to refresh audit badges.

---

### 3.12 Profile & System Diagnostics (`/app/profile`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| Profile                                               |
|                                                       |
| (Av) Alex                              [ Live API ]   |
|      ID: usr_organizer_01                             |
|                                                       |
| [!] Development identity. The backend trusts ID/role. |
|                                                       |
| APPEARANCE                                            |
| Theme:  [ System ]     [ Light ]     [ Dark* ]        |
|                                                       |
| DATA ON THIS DEVICE                                   |
| 2 circles, 2 rounds saved in this browser.            |
| [ Reset demo data ]             [ Clear saved ]       |
|                                                       |
| CONNECTION                                            |
| [ Check API ]                          (Button #55)   |
| Reachable (status: ok)                                |
|                                                       |
| MORE                                                  |
| Help & what’s connected                           [>] |
|                                                       |
| +---------------------------------------------------+ |
| | [ (signOut) Sign out ]               (Button #57) | |
| +---------------------------------------------------+ |
+-------------------------------------------------------+
```

#### Detailed Button Specifications

##### Button #52: Theme Segmented Buttons (`System`, `Light`, `Dark`)
- **Component:** `<button type="button" aria-pressed={pref === t.id} onClick={() => setPref(t.id)}>`.
- **Action:** Sets `document.documentElement.dataset.theme = pref`. Saves to `localStorage.chitcircle.theme`.

##### Button #53: "Reset demo data"
- **Component:** `<Button variant="secondary" small onClick={saved.resetToDefault}>`.
- **Condition:** Rendered in Demo mode only.
- **Action:** Flushes `localStorage` demo keys back to `DEMO_DEFAULT` fixture IDs.

##### Button #54: "Clear saved"
- **Component:** `<Button variant="secondary" small onClick={saved.clear}>`.
- **Action:** Clears saved circle and round ID arrays from device storage.

##### Button #55: "Check API" (Diagnostics Ping)
- **Component:** `<Button variant="secondary" small onClick={() => void check.run()} disabled={check.pending}>`.
- **Condition:** Rendered in Live mode only.
- **Double-Click Guard:** Handled by `useSingleFlight`. Label displays `"Checking…"`.
- **Backend Request:**
  - **Endpoint:** `GET /health`
  - **Response (200 OK):**
    ```json
    {"status": "ok"}
    ```
  - **UI Feedback:** Displays `"Reachable (ok)"` in green income tone. If unreachable, displays `"Network request failed"` in red danger text.

##### Button #57: "Sign out"
- **Component:** `<Button variant="secondary" block icon="signOut" onClick={...}>`.
- **Action:** Flushes `chitcircle.session.v1` from storage, resets state to signed-out, and routes to `/welcome`.

---

### 3.13 Help, FAQ & Capability Matrix (`/app/help`)

#### ASCII Wireframe
```
+-------------------------------------------------------+
| [<] Help & support                                    |
|                                                       |
| FREQUENTLY ASKED QUESTIONS                            |
| > What is a chit circle?                              |
| > When does a contribution count as paid?             |
| > Who decides auction winners and dividends?          |
| > Why can’t I see other members’ bids?                |
|                                                       |
| WHAT’S CONNECTED                                      |
| - View circle & members    GET /circles/{id}   [Conn] |
| - View round & payments    GET /cycles/{id}    [Conn] |
| - Round ledger activity    GET /ledger         [Conn] |
| - Auction bids             GET /auction/bids   [Conn] |
| - Settlement & recon       GET /settlements    [Conn] |
| - Create circles/cycles    POST /circles       [Conn] |
| - Online PayPal payment    POST /collections   [Pend] |
| - Live Payout release      POST /payout        [Stub] |
+-------------------------------------------------------+
```

#### Detailed Button Specifications
- **Button #58: FAQ Accordion Summaries (`<summary>`):** Native browser accessible disclosure. Expands answers explaining that money math is deterministic, server-calculated, and non-custodial.

---

### 3.14 System Fallback Screens (`/error.tsx`, `/not-found.tsx`)

#### Detailed Button Specifications
- **Button #59: "Try again" (`/error.tsx`):**  
  `<button className="btn btn--primary" onClick={reset}>`. Re-executes the failed Next.js React component tree.
- **Button #60: "Go to Home" (`/not-found.tsx`):**  
  `<Link className="btn btn--primary" href="/app/home">`. Restores navigation to home screen.

---

## 4. Agent Mandates & Approvals Queue Integration

The backend implements mandate-gated AI execution (`app/api/routes.py`, `adr/0007`). AI agents propose actions, but **only humans can approve money movement**. Approval issues a cryptographic, single-use, hash-locked mandate.

### Proposed UI Approvals Queue Card (For Organizer Dashboard)

```
+--- AGENT PROPOSED ACTION ---------------------------+
| (robot) Collections Reminder & Catch-up Invoice     |
| Member: Neha Gupta (4 days late on Round 2)         |
| Rationale: Grace period expired. Proposed polite    |
| catch-up invoice of ₹4,650 via PayPal.              |
|                                                     |
| [ Approve with Step-Up ]               (Button #61) |
| [ Revoke / Dismiss ]                   (Button #62) |
+-----------------------------------------------------+
```

### Endpoints for Approvals Queue Integration

1. **List Pending Proposals:**
   - **Endpoint:** `GET /circles/{circle_id}/proposed-actions`
   - **Response (200 OK):**
     ```json
     [
       {
         "id": "prop_01J88",
         "circle_id": "crcl_01H89XYZ",
         "kind": "invoice",
         "params": {
           "member_id": "usr_neha",
           "amount_minor": 465000,
           "currency": "INR",
           "cycle_id": "cycl_02"
         },
         "rationale": "Grace period expired on Nov 1st.",
         "expires_at": "2026-11-03T18:00:00Z"
       }
     ]
     ```

2. **Approve Proposal (Button #61):**
   - **Endpoint:** `POST /proposed-actions/{proposal_id}/approve`
   - **Request Body (`schemas.ApproveProposalIn`):**
     ```json
     {
       "step_up_method": "BIOMETRIC",
       "step_up_evidence": {"device_signature": "sig_abc123"},
       "cap_minor": 465000
     }
     ```
   - **Backend Behavior:** Generates single-use `Mandate` locked to exact amount, recipient, and cycle.

3. **Execute Mandate:**
   - **Endpoint:** `POST /mandates/{mandate_id}/execute`
   - **Backend Behavior:** Executes the locked financial action through the appropriate payment gateway.

---

## 5. PayPal & Payment Webhooks Architecture

The payment flow isolates sensitive payment credentials on the server. Webhooks are cryptographically validated before any ledger event is written.

```
+-------------+         +-----------------+         +------------------+         +---------------+
|   Member    |         | Next.js Client  |         | FastAPI Backend  |         |    PayPal     |
+------+------+         +--------+--------+         +--------+---------+         +-------+-------+
       |                         |                           |                           |
       | Tap "Pay Contribution"  |                           |                           |
       +------------------------>+ POST /collections/create  |                           |
       |                         +-------------------------->+ Create Invoice / Order    |
       |                         |                           +-------------------------->+
       |                         |                           | Return approval link      |
       |                         | Return checkout URL       |<= = = = = = = = = = = = = +
       |                         |< - - - - - - - - - - - - -+                           |
       | Redirect to PayPal      |                           |                           |
       +================================================================================>+
       | Complete Sandbox Payment                                                        |
       +-------------------------------------------------------------------------------->+
       |                                                     |                           |
       |                                                     | HTTP POST Webhook         |
       |                                                     | (/webhooks/provider)      |
       |                                                     | Headers: HMAC Signature   |
       |                                                     +<--------------------------+
       |                                                     |                           |
       |                                                     | 1. Verify Signature       |
       |                                                     | 2. Persist Raw Callback   |
       |                                                     | 3. Celery: Ingest Event   |
       |                                                     | 4. Ledger: PAYMENT_CONFIRMED
       |                                                     |                           |
```

### Webhook Verification Rules (`POST /webhooks/provider`)
- **Security:** Verified by `HmacVerifier` or PayPal Certificate headers (`PAYPAL-TRANSMISSION-SIG`).
- **Processing:** Two-phase execution. Phase A durably stores the raw body and returns `200 OK`. Phase B parses and records ledger entries asynchronously in Celery workers.
- **Idempotency:** Transactions are deduplicated by `provider_txn_id`. Duplicate callbacks do not create duplicate ledger records.

---

## 6. Backend Engineer Integration Checklist

When integrating the backend with this frontend, follow this verification checklist:

- [ ] **1. Enable Reverse Proxy Paths:**  
  Verify `frontend/next.config.mjs` contains all needed prefixes in `rewrites()`:
  `['health', 'circles', 'cycles', 'settlements', 'ledger', 'auth', 'collections', 'mandates', 'ops']`.
- [ ] **2. Check Environment Variables:**  
  Ensure `frontend/.env.local` is present with:
  ```env
  CHITCIRCLE_API_URL=http://localhost:8000
  NEXT_PUBLIC_LIVE_API_ENABLED=true
  NEXT_PUBLIC_DEFAULT_CURRENCY=INR
  NEXT_PUBLIC_PAYOUT_GATEWAY=stub
  ```
- [ ] **3. Run FastAPI Backend:**  
  ```bash
  cd backend
  source venv/bin/activate
  uvicorn app.main:app --reload --port 8000
  ```
- [ ] **4. Test Health Check from Browser:**  
  Visit `http://localhost:3000/app/profile`, click **Check API**, and verify green status: *"Reachable (ok)"*.
- [ ] **5. Test Circle Creation Flow:**  
  Open modal via **Open a circle** -> Switch to **Create New Circle** tab -> Fill Name & Total Value -> Click **Create Circle on Server**. Confirm `POST /circles` returns `201 Created` and redirect opens the new circle detail screen.
- [ ] **6. Test Round Creation:**  
  On the newly created circle's **Overview** tab, click **Start Next Round**. Confirm `POST /circles/{id}/cycles` generates Round 1 in `DRAFT` state.
- [ ] **7. Verify All Automated Frontend Tests Pass:**  
  ```bash
  cd frontend
  npm test
  ```
  Ensure all 64+ test cases pass without warnings.

