"""SolarSight LK API: ingest readings from solar sites and expose operator-facing views."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import __version__, db, forecast
from .simulator import demand_factor

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="SolarSight LK", version=__version__,
              description="Research prototype. All demo data is simulated.")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def require_key(x_api_key: str | None = Header(default=None)):
    """If SOLARSIGHT_API_KEY is set, write endpoints require a matching X-API-Key header."""
    expected = os.environ.get("SOLARSIGHT_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


class Site(BaseModel):
    site_id: str = Field(min_length=1, max_length=32)
    district: str = Field(min_length=1, max_length=64)
    capacity_kw: float = Field(gt=0, le=100_000)


class Reading(BaseModel):
    site_id: str
    ts: str
    power_kw: float = Field(ge=0, le=100_000)

    @field_validator("ts")
    @classmethod
    def _iso_utc(cls, v: str) -> str:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            raise ValueError("timestamp must include a timezone offset")
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@app.post("/api/sites", dependencies=[Depends(require_key)])
def upsert_sites(sites: list[Site]):
    with db.connect() as c:
        c.executemany(
            "INSERT INTO sites (site_id, district, capacity_kw) VALUES (?,?,?) "
            "ON CONFLICT(site_id) DO UPDATE SET district=excluded.district, capacity_kw=excluded.capacity_kw",
            [(s.site_id, s.district, s.capacity_kw) for s in sites])
    return {"upserted": len(sites)}


@app.get("/api/sites")
def list_sites():
    with db.connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM sites ORDER BY district, site_id")]


@app.post("/api/readings", dependencies=[Depends(require_key)])
def ingest(readings: list[Reading]):
    if len(readings) > 5000:
        raise HTTPException(status_code=413, detail="send at most 5000 readings per request")
    with db.connect() as c:
        known = {r["site_id"] for r in c.execute("SELECT site_id FROM sites")}
        good = [(r.site_id, r.ts, r.power_kw) for r in readings if r.site_id in known]
        before = c.total_changes
        c.executemany("INSERT OR IGNORE INTO readings (site_id, ts, power_kw) VALUES (?,?,?)", good)
        inserted = c.total_changes - before
    return {"inserted": inserted, "rejected_unknown_site": len(readings) - len(good)}


def _totals(c, since: str | None = None):
    q = "SELECT ts, SUM(power_kw) AS kw FROM readings"
    args = []
    if since:
        q += " WHERE ts >= ?"
        args.append(since)
    q += " GROUP BY ts ORDER BY ts"
    return [(r["ts"], r["kw"]) for r in c.execute(q, args)]


@app.get("/api/overview")
def overview(hours: int = 48):
    """Total solar output per timestamp plus a SIMULATED demand curve for context."""
    with db.connect() as c:
        capacity = c.execute("SELECT COALESCE(SUM(capacity_kw),0) AS cap FROM sites").fetchone()["cap"]
        rows = _totals(c)
    if not rows:
        return {"points": [], "installed_kw": capacity}
    cutoff = datetime.fromisoformat(rows[-1][0]) - timedelta(hours=hours)
    points = []
    for ts, kw in rows:
        dt = datetime.fromisoformat(ts)
        if dt < cutoff:
            continue
        demand = round(demand_factor(dt, low_demand_day=False) * capacity * 0.75, 1)
        points.append({"ts": ts, "solar_kw": round(kw, 1), "demand_kw_simulated": demand,
                       "solar_share": round(kw / demand, 3) if demand else None})
    return {"points": points, "installed_kw": round(capacity, 1),
            "note": "Demand is a simulated, illustrative curve, not real data."}


@app.get("/api/districts")
def districts():
    """Latest output and installed capacity per district."""
    with db.connect() as c:
        latest = c.execute("SELECT MAX(ts) AS ts FROM readings").fetchone()["ts"]
        if not latest:
            return {"ts": None, "districts": []}
        rows = c.execute(
            "SELECT s.district, COUNT(*) AS sites, SUM(s.capacity_kw) AS capacity_kw, "
            "COALESCE(SUM(r.power_kw),0) AS power_kw FROM sites s "
            "LEFT JOIN readings r ON r.site_id = s.site_id AND r.ts = ? GROUP BY s.district ORDER BY s.district",
            (latest,)).fetchall()
    return {"ts": latest, "districts": [
        {"district": r["district"], "sites": r["sites"], "capacity_kw": round(r["capacity_kw"], 1),
         "power_kw": round(r["power_kw"], 1),
         "utilisation": round(r["power_kw"] / r["capacity_kw"], 3) if r["capacity_kw"] else 0}
        for r in rows]}


@app.get("/api/forecast")
def get_forecast():
    """Baseline forecast for the next 24 hours (same time-of-day average) with a measured error."""
    with db.connect() as c:
        rows = _totals(c)
    if len(rows) < 96:
        raise HTTPException(status_code=409, detail="need at least 2 days of history for a forecast")
    last = datetime.fromisoformat(rows[-1][0])
    times = [last + timedelta(minutes=30 * (i + 1)) for i in range(48)]
    slots = [t.strftime("%H:%M") for t in times]
    values = forecast.forecast_next_day(rows, slots)
    return {
        "method": "same time-of-day average over past days (baseline)",
        "points": [{"ts": t.strftime("%Y-%m-%dT%H:%M:%S+00:00"), "solar_kw_forecast": v}
                   for t, v in zip(times, values)],
        "evaluation_last_day": forecast.evaluate(rows) if len(rows) > 96 else None,
    }
