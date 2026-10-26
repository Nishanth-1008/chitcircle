# 04. Caching Strategy

## 1. Principles

1. **Cache views, never decisions.** A cache may serve what a screen shows. It may never supply a number that decides who gets paid, whether a bid is valid, or whether a payout is approved.
2. **The database is always authoritative.** If Redis is down, the system slows down; it does not become wrong.
3. **Version, don't guess.** Cache keys carry the circle's `ledger_seq`, so stale data is unreachable instead of expiring eventually.
4. **Cache only what is read far more than it changes.** Dashboards and timelines yes; per-request lookups that are already cheap, no.

## 2. Layers

| Layer | What | Mechanism |
|---|---|---|
| Browser / app | Last-known screen state | TanStack Query with stale-while-revalidate; PWA caches the shell and read-only data |
| CDN | Static assets, marketing pages, public docs | Long TTL, hashed filenames |
| HTTP | Read-model endpoints | `ETag` from `ledger_seq`; `If-None-Match` returns 304 with no body |
| Redis (cache) | Read models, immutable lookups, derived data | Cache-aside with versioned keys |
| Process memory | Tiny static data (presets, currency table) | Loaded at start, invalidated on deploy |

## 3. What to cache

| Item | Key pattern | TTL / invalidation |
|---|---|---|
| **Ruleset by version** | `ruleset:{circle_id}:{version}` | **No expiry.** Rulesets are immutable and fingerprinted |
| Circle timeline (member x cycle grid) | `tl:{circle_id}:{ledger_seq}` | Old versions expire after 10 minutes; new seq means new key |
| Organizer dashboard summary | `dash:{circle_id}:{ledger_seq}` | Same |
| Member private view | `mv:{circle_id}:{member_id}:{ledger_seq}` | Same |
| Jurisdiction presets | in-process | Until deploy |
| Risk indicators | `risk:{circle_id}:{member_id}:{ledger_seq}` | 5 minutes (advisory only) |
| Agent explanations and summaries | `llm:{hash(inputs)}` | 24 hours; inputs include the settlement fingerprint |
| Provider OAuth token | `pp:token:{env}` | TTL = token lifetime minus 5 minutes, single-flight refresh |
| Permission lookups (role in circle) | `perm:{user}:{circle}` | 60 seconds; busted on role change |
| Rate limit counters | `rl:{scope}:{id}:{window}` | Window length |
| Idempotency fast path | `idem:{actor}:{key}` | 24 hours (table is authoritative) |

## 4. What never to cache (read from the primary under lock)

- Obligation balances and arrears used for bid eligibility
- Bid validity checks and the current winner calculation
- Settlement amounts, approvals, payout state
- Reconciliation inputs and results
- Anything inside a transaction that writes money state

## 5. Invalidation by version

Every ledger write increments `circles.ledger_seq` in the same transaction. A projection worker consumes the outbox and rebuilds read models for that circle.

```python
def get_timeline(circle_id: str) -> dict:
    seq = seq_cache.get(circle_id) or db.fetch_ledger_seq(circle_id)   # one tiny indexed read
    key = f"tl:{circle_id}:{seq}"
    hit = redis.get(key)
    if hit:
        return json.loads(hit)
    with single_flight(key, ttl=5):                  # stampede guard
        hit = redis.get(key)
        if hit:
            return json.loads(hit)
        data = build_timeline_from_read_model(circle_id, seq)
        redis.setex(key, 600 + random.randint(0, 120), json.dumps(data))  # jittered TTL
        return data
```

Responses return `ETag: "{circle_id}:{seq}"`; clients revalidate cheaply.

## 6. Stampede and failure behaviour

- **Single-flight lock** per key so one request rebuilds while others wait briefly or serve the previous version.
- **Jittered TTLs** so keys written together do not expire together.
- **Stale-while-revalidate** for non-critical views: serve the previous seq's value and refresh in the background.
- **Timeouts** on Redis calls of 50 to 100 ms. A timeout is a miss, not an error.
- **Circuit breaker** around Redis; when open, serve from the database with a lower rate limit on heavy endpoints.

## 7. Redis topology

Use **separate Redis instances (or clusters) by purpose**, because the eviction policies conflict:

| Instance | Purpose | Eviction | Persistence |
|---|---|---|---|
| `cache` | Read models, lookups | `allkeys-lru` | Off |
| `queue` | Job broker | **`noeviction`** | On (AOF) |
| `rt` | Pub/sub for live auctions | n/a | Off |
| `rl` | Rate limits (may share with `cache` early) | `volatile-ttl` | Off |

Losing `cache` or `rt` must be harmless. Losing `queue` must be recoverable from the outbox (jobs are re-derivable from database state).

## 8. Real-time data and caching

Bids are written to PostgreSQL first. Redis pub/sub only carries a small "something changed" signal so connected clients refetch the (cached) view. Do not store bid truth in Redis.

## 9. Sizing and metrics

- Start with a 1 to 2 GB cache instance; the working set is small (5,000 circles x a few KB per view).
- Track: hit rate per key family, rebuild time, stampede waits, Redis latency p99, evictions. Target hit rate above 90% on timeline and dashboard.

## 10. Anti-patterns to avoid

- Caching a number and then using it in an `UPDATE`.
- Per-user caches of data that is the same for the whole circle (cache once per circle, filter per member in code).
- Long TTLs as the only invalidation strategy.
- Storing PII in cache keys or unencrypted values.
