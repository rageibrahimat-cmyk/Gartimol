# Gartimol Trust Score Service (MVP)

Implements `Gartimol_TrustScore_Service_Architecture_v1.md` end to end,
per the handoff notes in its §8.

## Structure

```
app/
  schemas.py    Pydantic models (§2 domain shapes + API payloads)
  scoring.py    Pure computation logic — §3.1/3.2/3.3, no I/O
  models.py     SQLAlchemy ORM — owns trust_score_snapshot only (§2);
                read-only reflections of PlanGoal/ActivityEvent/Alert
  db.py         Engine/session setup
  auth.py       JWT bearer, user_id-or-admin check (§4)
  router.py     The 4 endpoints in §4
  main.py       FastAPI app, mounts the router as its own module (§8)
  scheduler.py  15-minute polling recompute (§5) — no event bus, by design
tests/
  test_scoring.py   Null-handling cases from §3.3, written first per §8
```

## Setup

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/gartimol"
export JWT_SECRET="your-secret"
```

## Run tests

```bash
pytest tests/ -v
```

## Run the API

```bash
uvicorn app.main:app --reload
```

## Run the scheduled recompute worker (separate process)

```bash
python -m app.scheduler
```

## What's deliberately NOT here (per §7 of the spec / MVP scope doc)

- Network Resonance, Resistance Conversion, Historical Consistency — no
  data source exists yet; adding them means guessing weights.
- Real-time streaming — polling/on-demand recompute is sufficient for MVP.
- ML-based scoring — rule-based and transparent until there's history to
  validate a model against.
- Kafka/event sourcing — not needed until user volume justifies it (§5).

## Notes for whoever picks this up next

- `PlanGoalORM`, `ActivityEventORM`, `AlertORM` in `models.py` are marked
  `owned_by` in their table info — this service reads them but must never
  write to them (bounded context boundary, §1).
- `_persist_snapshot` always writes a row, even for insufficient-data
  states, so the audit trail in `inputs_snapshot` is complete (§6).
- `auth.py`'s `decode_jwt` is a placeholder HS256 stub — swap for your
  actual provider (Supabase Auth / Auth0, per the MVP stack doc) before
  shipping; don't hand-roll real auth beyond this scaffold.
