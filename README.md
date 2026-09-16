# Ironman Cycle Router

Plan training rides: loops from home, rides of a set distance that finish somewhere nearby, or
A-to-B trips.

Pick where you start and how far you want to ride. The planner builds several candidate rides on
real roads, bike paths, and trails, measures each one, and ranks them with a transparent weighted
formula. Results appear on a cycling map with an explanation for every rank.

**Live:** <https://cycling-route-three.vercel.app>

![CI](https://github.com/christghuynh/cycling-route/actions/workflows/ci.yml/badge.svg)

<!-- Screenshots: add docs/screenshots/*.png after running the app with a real ORS key. -->

## Features

- **Three trip types**
  - **Loop:** start and finish at the same place, e.g. "30 km from my house".
  - **Ride to:** ride a target distance and finish somewhere else, e.g. a café 5 km away.
  - **A → B:** get from one place to another, with alternative routes.
- **Autocomplete** for street addresses and places, ranked around the map you are looking at, so
  "Waterloo" means Waterloo, ON rather than Waterloo, IA. The app asks for your location on load
  to centre the map, and there is a **use my location** shortcut.
- **Bike type** (road, hybrid, mountain) selects the matching OpenRouteService cycling profile
- Several distinct candidate rides per search, tuned towards the target distance. Near-duplicates
  and rides that mostly double back on themselves are filtered out.
- Elevation profile and noise-filtered elevation gain
- An **estimated** safety score based on how much of the ride uses cycleways, paths, and quiet
  streets versus major roads, clearly labelled as a proxy
- Adjustable ranking weights with a per-route score breakdown
- A cycling map layer (CyclOSM) that shows bike lanes and trails
- Searches and routes stored in PostgreSQL and retrievable by id
- Per-client rate limiting, because the routing API key is shared by everyone using a deployment

## Tech stack

| Area | Tools |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), asyncpg, httpx |
| Frontend | React 19, TypeScript, Vite, Leaflet / react-leaflet |
| Data | OpenRouteService (routing, elevation, geocoding), OpenStreetMap / CyclOSM tiles |
| Database | PostgreSQL 16 |
| Quality | pytest, respx, ruff, mypy (strict), ESLint, Prettier, Vitest |
| Delivery | Docker, docker compose, nginx, GitHub Actions |

## Quick start (Docker)

1. Get a free OpenRouteService API key (no credit card, HeiGIT account):
   <https://openrouteservice.org/dev/#/signup>. It is the only key the app needs.
2. Create your env file and add the key:

   ```bash
   cp .env.example .env
   # edit .env and set ORS_API_KEY=...
   ```

3. Start everything:

   ```bash
   docker compose up --build
   ```

| Service | URL |
| --- | --- |
| App | <http://localhost:8080> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Health check | <http://localhost:8000/api/health> |

## Local development

**Prerequisites:** Python 3.11+, Node 20+ (CI uses 24), and PostgreSQL. The easiest way to get
PostgreSQL is `docker compose up db`.

### Backend

Dependencies live in `backend/pyproject.toml`, pinned by `uv.lock`. With
[uv](https://docs.astral.sh/uv/) installed:

```bash
cd backend
uv sync --extra dev              # creates .venv and installs everything
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

Settings come from environment variables, falling back to `.env` in the repository root (or in
`backend/`). See `app/core/config.py` for all options.

```bash
uv run pytest          # tests (no real external API calls)
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

### Frontend

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api to localhost:8000)
npm run lint
npm run format:check
npm test
npm run build
```

## How rides are generated

A routing engine only connects waypoints, so a "30 km loop from home" needs waypoints that add up
to about 30 km:

1. For each of 4 directions, place via points clockwise around a circle that passes through the
   start. For "ride to", the ride finishes at the destination instead. Clockwise loops mean mostly
   right turns in right-hand-traffic countries.
2. Solve the circle size so the straight-line path is the target distance divided by a road factor
   of 1.3.
3. Route through the waypoints on real roads and trails with OpenRouteService.
4. If the ride is more than 8% off target, recalculate the waypoints using the road factor actually
   observed in that direction, and route again.
5. Measure every ride: distance, climbing, way types, and how much it doubles back.
6. Drop near-duplicates and out-and-back rides when better options exist, then rank.

## How routes are scored

Each route gets three component scores from 0 to 100:

- **Distance:**
  - With a target: 100 at exactly the target, falling to 0 at 30% over or under.
  - Without a target (A → B): relative to the shortest route found. A route 50% longer scores 0.
- **Elevation:** based on climbing per km. Flat scores 100, and 25 m/km scores 0.
- **Estimated safety:** the distance-weighted average of way-type ratings. For example, cycleway
  is 100 and major road is 15.

The overall score is the weighted average using your preferences. If one factor is unavailable for
any route, it is dropped for all routes, so every route is compared on the same basis.

Full details are in [docs/architecture.md](docs/architecture.md).

> **About the safety score:** it is a proxy derived from OpenStreetMap way types. It does not
> reflect traffic volume, speed limits, lane quality, or collision history.

## API

Interactive docs are served at `/docs`.

### `POST /api/routes`

```json
{
  "mode": "loop",
  "start": { "label": "200 University Ave W, Waterloo, ON, Canada", "lat": 43.4723, "lon": -80.5449 },
  "target_distance_km": 30,
  "bike_type": "road",
  "preferences": { "distance_weight": 0.5, "elevation_weight": 0.2, "safety_weight": 0.3 }
}
```

- **`mode`:** `loop`, `distance_goal` (needs `destination`), or `point_to_point` (needs
  `destination`, and ignores `target_distance_km`).
- **Locations:** a `label` with `lat`/`lon`, as picked from autocomplete, or just a `label`, which
  is then geocoded.
- **`preferences`:** optional. Weights are normalised to sum to 1.

The response contains the search context (`mode`, `start`, `destination`, `target_distance_km`,
`preferences`, `warnings`) and ranked `routes`. Each route has distance, climbing, duration,
component and overall scores, `repeated_share`, a summary, highlights, way-type shares, geometry,
and an elevation profile.

### `GET /api/locations/autocomplete?q=Waterl&focus_lat=43.4&focus_lon=-80.5`

Place suggestions while typing. `q` needs at least 3 characters. The optional focus point biases
results towards it.

### `GET /api/routes/{route_id}`

Returns `{ "route": {...}, "search": {...} }` for a previously generated route.

### `GET /api/health`

Returns `{"status": "ok", "database": "ok"}`, or `503` if the database is unreachable.

### Errors

All errors use the same shape:

```json
{ "error": { "code": "invalid_trip", "message": "The finish is 24.1 km away in a straight line, so the target distance needs to be longer." } }
```

## Limitations and next steps

- **Minimal stopping** is not measured yet. The next step is counting traffic signals and stop
  signs along each ride from OpenStreetMap data.
- **Safety** is a way-type proxy. Real traffic or collision data would make it meaningful.
- **Quota:** each target-distance search makes up to 8 routing calls, and typing an address makes
  several geocoding calls. The free ORS plan allows about 40 routing requests per minute, which is
  roughly 5 searches per minute. The deployed app limits each client to 30 searches and 300
  autocomplete requests per hour (`ROUTE_REQUESTS_PER_HOUR`, `AUTOCOMPLETE_REQUESTS_PER_HOUR`).
- **Schema:** tables are created at startup. Add Alembic once the schema needs to change. If you
  ran an earlier version, drop the old database volume (`docker compose down -v`).
