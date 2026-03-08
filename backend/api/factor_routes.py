"""
Factor System API Routes

GET  /api/factors/library                       → Factor registry
GET  /api/factors/values?exchange=&symbol=&period= → Latest factor values
GET  /api/factors/effectiveness?exchange=&symbol=  → Effectiveness ranking
GET  /api/factors/effectiveness/{name}/history     → IC trend
GET  /api/factors/status                          → Engine status
POST /api/factors/compute                         → Manual trigger
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database.connection import SessionLocal
from services.factor_registry import FACTOR_REGISTRY, FACTOR_CATEGORIES, CATEGORY_LABELS

router = APIRouter(prefix="/api/factors", tags=["factors"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/library")
async def get_factor_library():
    """Return the full factor registry (no DB query needed)."""
    return {
        "factors": FACTOR_REGISTRY,
        "categories": FACTOR_CATEGORIES,
        "category_labels": CATEGORY_LABELS,
    }


@router.get("/values")
async def get_factor_values(
    symbol: str = Query(...),
    period: str = Query("1h"),
    exchange: str = Query("hyperliquid"),
    db: Session = Depends(get_db),
):
    """Return latest factor values for a symbol/period/exchange."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (factor_name)
            factor_name, factor_category, value, timestamp
        FROM factor_values
        WHERE symbol = :sym AND period = :p AND exchange = :ex
        ORDER BY factor_name, timestamp DESC
    """), {"sym": symbol, "p": period, "ex": exchange}).fetchall()

    return {
        "symbol": symbol, "period": period, "exchange": exchange,
        "values": [
            {"factor_name": r[0], "category": r[1], "value": r[2], "timestamp": r[3]}
            for r in rows
        ],
    }


@router.get("/effectiveness")
async def get_factor_effectiveness(
    symbol: str = Query(...),
    period: str = Query("1h"),
    forward_period: str = Query("4h"),
    exchange: str = Query("hyperliquid"),
    sort_by: str = Query("icir"),
    db: Session = Depends(get_db),
):
    """Return effectiveness ranking for a symbol/period/forward_period."""
    valid_sorts = {"icir", "ic_mean", "win_rate", "sample_count"}
    col = sort_by if sort_by in valid_sorts else "icir"

    rows = db.execute(text(f"""
        SELECT DISTINCT ON (factor_name)
            factor_name, factor_category, ic_mean, ic_std, icir,
            win_rate, decay_half_life, sample_count, calc_date
        FROM factor_effectiveness
        WHERE symbol = :sym AND period = :p AND forward_period = :fp AND exchange = :ex
        ORDER BY factor_name, calc_date DESC
    """), {"sym": symbol, "p": period, "fp": forward_period, "ex": exchange}).fetchall()

    items = [
        {
            "factor_name": r[0], "category": r[1],
            "ic_mean": r[2], "ic_std": r[3], "icir": r[4],
            "win_rate": r[5], "decay_half_life": r[6],
            "sample_count": r[7], "calc_date": str(r[8]),
        }
        for r in rows
    ]
    items.sort(key=lambda x: abs(x.get(col) or 0), reverse=True)

    return {
        "symbol": symbol, "period": period,
        "forward_period": forward_period, "exchange": exchange,
        "items": items,
    }


@router.get("/effectiveness/{factor_name}/history")
async def get_effectiveness_history(
    factor_name: str,
    symbol: str = Query(...),
    period: str = Query("1h"),
    forward_period: str = Query("4h"),
    exchange: str = Query("hyperliquid"),
    days: int = Query(30),
    db: Session = Depends(get_db),
):
    """Return IC trend over time for a specific factor."""
    cutoff = date.today() - timedelta(days=days)
    rows = db.execute(text("""
        SELECT calc_date, ic_mean, icir, win_rate, sample_count
        FROM factor_effectiveness
        WHERE factor_name = :fn AND symbol = :sym AND period = :p
            AND forward_period = :fp AND calc_date >= :cutoff
        ORDER BY calc_date
    """), {"fn": factor_name, "sym": symbol, "p": period,
           "fp": forward_period, "cutoff": cutoff}).fetchall()

    return {
        "factor_name": factor_name,
        "history": [
            {"date": str(r[0]), "ic_mean": r[1], "icir": r[2],
             "win_rate": r[3], "sample_count": r[4]}
            for r in rows
        ],
    }


@router.get("/status")
async def get_factor_status(db: Session = Depends(get_db)):
    """Return engine status with per-exchange last compute time."""
    import os
    enabled = os.getenv("FACTOR_ENGINE_ENABLED", "false").lower() == "true"

    from services.factor_computation_service import factor_computation_service

    stats = db.execute(text("""
        SELECT COUNT(*), COUNT(DISTINCT symbol), MAX(timestamp)
        FROM factor_values
    """)).fetchone()

    eff_stats = db.execute(text("""
        SELECT COUNT(*), MAX(calc_date) FROM factor_effectiveness
    """)).fetchone()

    return {
        "enabled": enabled,
        "total_factor_values": stats[0] if stats else 0,
        "symbols_covered": stats[1] if stats else 0,
        "latest_computation_ts": stats[2] if stats else None,
        "total_effectiveness_records": eff_stats[0] if eff_stats else 0,
        "latest_effectiveness_date": str(eff_stats[1]) if eff_stats and eff_stats[1] else None,
        "registered_factors": len(FACTOR_REGISTRY),
        "last_compute_time": {
            "hyperliquid": factor_computation_service.get_last_compute_time("hyperliquid"),
            "binance": factor_computation_service.get_last_compute_time("binance"),
        },
        "compute_interval_seconds": 3600,
    }


class ComputeRequest(BaseModel):
    exchange: str = "hyperliquid"
    period: str = "1h"


@router.post("/compute")
async def trigger_compute(req: ComputeRequest, db: Session = Depends(get_db)):
    """Manually trigger factor values + effectiveness computation."""
    from services.factor_computation_service import factor_computation_service
    from services.factor_effectiveness_service import factor_effectiveness_service

    val_result = factor_computation_service.compute_now(req.exchange, req.period)
    eff_result = factor_effectiveness_service.compute_for_exchange(db, req.exchange, req.period)

    return {
        "exchange": req.exchange,
        "values_computed": val_result.get("computed", 0),
        "effectiveness_computed": eff_result.get("computed", 0),
    }
