# Sponsor Tools Plan

Sponsor tools are optional for the hackathon (any tool works as long as PayPal integration is central), but sponsors offer separate prizes. Prefer depth over breadth: use a few tools well and describe each in the submission.

| Tool | What it is | Role in ChitCircle | Phase | Priority |
|---|---|---|---|---|
| **Render** | Hosting; managed Postgres and Redis-compatible store; background workers; cron and workflows | Host API, worker, database, scheduled cycle jobs | 0 to 1, continues in 2 to 3 | High |
| **Bryntum** | Scheduler, Gantt and Calendar components (trial available) | Member-by-month timeline: paid, late, pending, auction month, winner | 0 to 1, web only | High |
| **Postman** | API design, testing and monitoring; public PayPal collection | Test PayPal sandbox calls and our own API; CI runs; production monitors | 0 to 2 | High |
| **Zapier MCP** | Lets agents act across thousands of apps | Reminder delivery and approvals via apps members already use | 1 and 4 | Medium |
| **APIMatic** | Context plugin giving the coding agent PayPal API context | Faster, more accurate PayPal integration code | 0 to 1 | Medium (low effort) |
| **AG Grid / AG Studio** | Data grid and embedded dashboards with an agent framework | Ledger grid or organizer widgets; choose Bryntum or AG as the star UI | 1 stretch, 4 | Optional |
| **Elastic** | Search, analytics and agent builder | Ledger search and explainer over audit data | 3+ | Optional |
| **Astropods** | Runs and monitors agents | Overlaps with hosting and workers | none | Skip for now |
| **Channel3** | Product search for shopping agents | Not relevant | none | Skip |
| **KERNEL** | Browser infrastructure for agents | Not relevant | none | Skip |

## Submission notes

- State plainly which tools were used, for what, and where in the code.
- Keep tool-specific code isolated (adapters, components) so removing a sponsor tool later does not touch the engine.
- Check each sponsor's prize rules and any free-credit or trial terms on the hackathon page before relying on them.
