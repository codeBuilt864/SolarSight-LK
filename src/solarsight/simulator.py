"""Simulated solar sites and a simulated national demand curve.

IMPORTANT: everything produced here is SIMULATED. It is a stand-in for real inverter
data so the pipeline can be built and tested end to end before any real data exists.
"""
import argparse
import math
import random
from datetime import datetime, timedelta, timezone

LOCAL_OFFSET_H = 5.5  # Sri Lanka standard time, UTC+05:30
STEP_MIN = 30

# (district, number of sites) - invented for the simulation
DISTRICTS = [("Colombo", 6), ("Kandy", 4), ("Trincomalee", 3), ("Jaffna", 3), ("Hambantota", 4)]


def make_sites(seed: int = 7):
    rng = random.Random(seed)
    sites = []
    for district, n in DISTRICTS:
        for i in range(n):
            sites.append({
                "site_id": f"{district[:3].upper()}-{i + 1:02d}",
                "district": district,
                "capacity_kw": round(rng.uniform(5, 60), 1),
            })
    return sites


def clear_sky_factor(ts_utc: datetime) -> float:
    """0..1 bell-shaped sun curve, peaking at local solar noon, zero at night."""
    local = ts_utc + timedelta(hours=LOCAL_OFFSET_H)
    hour = local.hour + local.minute / 60
    if hour < 6 or hour > 18:
        return 0.0
    return math.sin(math.pi * (hour - 6) / 12) ** 1.3


def site_power(site: dict, ts_utc: datetime, cloud: float) -> float:
    return round(site["capacity_kw"] * clear_sky_factor(ts_utc) * cloud, 3)


def demand_factor(ts_utc: datetime, low_demand_day: bool) -> float:
    """Illustrative national demand shape (relative units 0..1), with a lower daytime on holidays."""
    local = ts_utc + timedelta(hours=LOCAL_OFFSET_H)
    h = local.hour + local.minute / 60
    base = 0.55 + 0.15 * math.sin(math.pi * (h - 6) / 12) if 6 <= h <= 18 else 0.5
    evening_peak = 0.45 * math.exp(-((h - 19.0) ** 2) / 3.0)
    value = base + evening_peak
    if low_demand_day:
        value *= 0.8 if 8 <= h <= 17 else 0.9
    return round(value, 4)


def generate(days: int = 7, seed: int = 7, end: datetime | None = None):
    """Yield (site, ts, power_kw) readings for `days` days ending at `end` (UTC, default: now)."""
    rng = random.Random(seed)
    end = end or datetime.now(timezone.utc)
    end = end.replace(minute=(end.minute // 30) * 30, second=0, microsecond=0)
    sites = make_sites(seed)
    steps = days * 24 * 60 // STEP_MIN
    for k in range(steps):
        ts = end - timedelta(minutes=STEP_MIN * (steps - 1 - k))
        # one cloud factor per district per step, plus small per-site noise
        cloud_by_district = {}
        for s in sites:
            d = s["district"]
            if d not in cloud_by_district:
                day_index = (ts + timedelta(hours=LOCAL_OFFSET_H)).date().toordinal()
                day_mood = random.Random(f"{seed}-{d}-{day_index}").uniform(0.55, 1.0)
                cloud_by_district[d] = day_mood
            cloud = min(1.0, max(0.1, cloud_by_district[d] + rng.uniform(-0.08, 0.08)))
            yield s, ts, site_power(s, ts, cloud)


def main():
    p = argparse.ArgumentParser(description="Post simulated solar readings to a SolarSight API.")
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--api-key", default=None)
    args = p.parse_args()

    import json
    import urllib.request

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    def post(path, payload):
        req = urllib.request.Request(args.api + path, json.dumps(payload).encode(), headers, method="POST")
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    post("/api/sites", make_sites())
    batch, total = [], 0
    for site, ts, kw in generate(days=args.days):
        batch.append({"site_id": site["site_id"], "ts": ts.isoformat(), "power_kw": kw})
        if len(batch) == 1000:
            total += post("/api/readings", batch)["inserted"]
            batch = []
    if batch:
        total += post("/api/readings", batch)["inserted"]
    print(f"Posted {total} simulated readings to {args.api}")


if __name__ == "__main__":
    main()
