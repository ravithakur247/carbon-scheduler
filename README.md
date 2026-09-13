# Carbon-Aware Inference Scheduler

A middleware layer that delays and routes non-urgent AI inference jobs to whenever/wherever
the electricity grid is cleanest, instead of running everything immediately. Built and
tested end-to-end as a working MVP — not just a sketch.

## What's actually implemented

- **FastAPI gateway** (`POST /infer`) that accepts jobs and tags them urgent / non-urgent
- **Carbon-aware decision engine** (`app/scheduler.py`) — checks live grid carbon intensity,
  runs the job immediately if it's clean enough, otherwise queues it and re-checks on a
  timer, forcing execution once a max-wait deadline is hit so nothing waits forever
- **Multi-region routing** — picks the greenest of several configured grid regions for each job
- **Redis-backed queue** (`app/store.py`) — a sorted set keyed by "next check time," survives
  restarts, no in-memory state to lose
- **Pluggable carbon data source** (`app/carbon.py`):
  - `mock` (default) — a deterministic simulated day/night carbon curve per region, so the
    whole thing runs and demos with zero API keys or network access
  - `electricitymaps` — real integration with the Electricity Maps API, one env var away
- **Transparency metrics per job** — energy estimate, actual CO₂ emitted, CO₂ saved vs. running
  immediately in the home region, and delay time
- **Live dashboard** at `/dashboard` — auto-refreshing view of current grid intensity per
  region, running totals, and a job table
- **Docker Compose** for one-command startup with Redis included

## Quick start

### Option A — Docker (simplest)
```bash
docker compose up --build
```
Then open http://localhost:8000/dashboard

### Option B — Local Python
```bash
# 1. Start Redis (or use docker: `docker run -p 6379:6379 redis:7-alpine`)
redis-server --daemonize yes

# 2. Install deps
pip install -r requirements.txt

# 3. Copy env template (defaults work out of the box, using the mock carbon provider)
cp .env.example .env

# 4. Run
uvicorn app.main:app --reload
```
Then open http://localhost:8000/dashboard

## Try it

```bash
# Check current carbon intensity across regions
curl http://localhost:8000/carbon

# Submit an urgent job — runs immediately, routed to the greenest available region
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarize this contract", "urgent": true, "estimated_tokens": 800}'

# Submit a non-urgent batch job — queues if the grid is currently dirty everywhere,
# and runs automatically once it's clean or the max-wait deadline is hit
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Nightly contract batch", "urgent": false, "estimated_tokens": 2000}'

# Check a job's status / final metrics
curl http://localhost:8000/status/<job_id>

# Aggregate stats (CO2 saved, queue depth, etc.)
curl http://localhost:8000/stats
```

I ran this exact flow while building it: with the clean threshold set below the current
grid intensity everywhere, a submitted job sat in `queued` status, then the background
scheduler picked it up and force-ran it once its max-wait deadline passed — landing in the
`EU-FR` region (lowest simulated intensity), reporting energy used, actual CO₂ emitted, CO₂
saved vs. the home-region baseline, and delay time. Stats accumulated correctly across
multiple jobs.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `CARBON_PROVIDER` | `mock` | `mock` or `electricitymaps` |
| `ELECTRICITYMAPS_API_KEY` | _(empty)_ | Required if using the real provider |
| `ELECTRICITYMAPS_ZONE` | `US-MIDA-PJM` | Zone code for the real provider (single-region mode) |
| `CLEAN_THRESHOLD_G_PER_KWH` | `250` | Below this, a job is allowed to run |
| `POLL_INTERVAL_SECONDS` | `15` | How often queued jobs are re-checked |
| `MAX_WAIT_MINUTES` | `60` | Hard deadline — job runs regardless once hit |
| `ENERGY_PER_1K_TOKENS_KWH` | `0.0024` | Used for the simulated energy estimate |
| `REGIONS` | `US-MIDA-PJM,US-CAL-CISO,EU-FR` | Regions to route across; first = "home" (submit-time baseline) |

## Architecture

```
Client → POST /infer → FastAPI Gateway
                             │
                    checks carbon now (all regions)
                             │
              clean enough? ──yes──→ run now, routed to greenest region
                             │
                             no
                             │
                             ▼
                    Redis sorted-set queue
                    (score = next check time)
                             │
              background scheduler loop (asyncio task)
              polls every POLL_INTERVAL_SECONDS,
              re-checks carbon, force-runs at deadline
                             │
                             ▼
                    Inference worker (mock)
                    → energy, CO2 actual, CO2 saved, stats
```

## Going from MVP to production

Two mock pieces are clearly isolated so they're a single-file swap:

1. **Real carbon data** — `app/carbon.py`: `ElectricityMapsProvider` is already implemented;
   set `CARBON_PROVIDER=electricitymaps` and `ELECTRICITYMAPS_API_KEY`. WattTime or CO2 Signal
   would follow the same `CarbonProvider` interface.
2. **Real inference** — `app/inference.py`: replace `run_inference()` with a call to your
   vLLM / TGI / llama.cpp endpoint. Keep returning token count (or pull energy straight from
   GPU power draw via `nvidia-smi` / DCGM if you're instrumenting directly — that'd be more
   accurate than the token-based estimate used here).

Other things worth doing before real traffic:
- Move the scheduler loop to a separate worker process (or Celery/arq) instead of an
  in-process asyncio task, so gateway restarts don't interrupt in-flight scheduling
- Add carbon **forecasts** (Electricity Maps and WattTime both offer them) so the scheduler
  can make a smarter "wait 20 more minutes, it'll drop further" decision instead of only
  reacting to the current reading
- Add per-tenant/job-type SLAs instead of one global threshold and wait time
- Auth on the `/infer` endpoint

## License

MIT — see [LICENSE](LICENSE).
