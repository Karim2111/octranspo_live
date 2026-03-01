
## Schema & Relationships

```
routes ──< trips ──< stop_times >── stops
              │
              └── calendar (via service_id)
```

| Table | Primary Key | Links to |
|-------|-------------|----------|
| `routes` | `route_id` | — |
| `trips` | `trip_id` | `routes.route_id` |
| `stop_times` | `(trip_id, stop_sequence)` | `trips.trip_id`, `stops.stop_id` |
| `stops` | `stop_id` | — |
| `calendar` | `service_id` | referenced by `trips.service_id` |

**How a route flows through the DB:**

1. A **route** (e.g. Route 95) has many **trips** — each trip is one run of that route in a given direction.
2. Each **trip** is tied to a **service** (via `service_id`) which defines what days it runs (weekday, Saturday, Sunday) through the **calendar** table.
3. Each **trip** has an ordered list of **stop_times** — one row per stop, with `arrival_time`/`departure_time` and a `stop_sequence` position.
4. Each stop_time points to a **stop** (the physical bus stop with lat/lon coordinates).

