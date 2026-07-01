"""
App entrypoint. Per §8 of the architecture spec: "This service should be
a separate module/router, not entangled with Alert or Ledger logic."
Mount this router into your overall API gateway alongside the Alerting
and Ledger routers, each owning their own bounded context.
"""
from fastapi import FastAPI

from app.router import router as trust_score_router

app = FastAPI(title="Gartimol Trust Score Service", version="1.0.0")

app.include_router(trust_score_router)


@app.get("/health")
def health():
    return {"status": "ok"}
