"""Baseline short-term forecast: the average of the same time-of-day over past days.

This is deliberately simple. It is the benchmark that any better model (for example one using
weather data) must beat. Forecast quality is measured, not assumed: see `evaluate`.
"""
from collections import defaultdict
from statistics import mean


def slot_of(ts_iso: str) -> str:
    """Time-of-day slot, e.g. '06:30', from an ISO timestamp (UTC)."""
    return ts_iso[11:16]


def same_slot_average(series: list[tuple[str, float]]) -> dict[str, float]:
    by_slot = defaultdict(list)
    for ts, kw in series:
        by_slot[slot_of(ts)].append(kw)
    return {slot: mean(vals) for slot, vals in by_slot.items()}


def forecast_next_day(series: list[tuple[str, float]], slots: list[str]) -> list[float]:
    """Forecast one value per requested time-of-day slot."""
    avg = same_slot_average(series)
    return [round(avg.get(s, 0.0), 3) for s in slots]


def evaluate(series: list[tuple[str, float]], holdout_points: int = 48) -> dict:
    """Train on everything except the last `holdout_points` and report the error on the rest."""
    if len(series) <= holdout_points + 48:
        raise ValueError("not enough history to evaluate")
    train, test = series[:-holdout_points], series[-holdout_points:]
    avg = same_slot_average(train)
    errors = [abs(avg.get(slot_of(ts), 0.0) - actual) for ts, actual in test]
    actual_sum = sum(a for _, a in test) or 1.0
    return {
        "mae_kw": round(mean(errors), 2),
        "mae_percent_of_mean": round(100 * mean(errors) / (actual_sum / len(test)), 1),
        "holdout_points": holdout_points,
    }
