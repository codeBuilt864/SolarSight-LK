import pytest

from solarsight import forecast


def make_series(days, value_by_slot):
    out = []
    for d in range(days):
        for slot, v in value_by_slot.items():
            out.append((f"2026-10-{10 + d:02d}T{slot}:00+00:00", v))
    return out


def test_same_slot_average():
    series = [("2026-10-01T06:00:00+00:00", 10.0), ("2026-10-02T06:00:00+00:00", 20.0)]
    assert forecast.same_slot_average(series) == {"06:00": 15.0}


def test_forecast_uses_requested_slots():
    series = [("2026-10-01T06:00:00+00:00", 10.0), ("2026-10-02T06:00:00+00:00", 20.0)]
    assert forecast.forecast_next_day(series, ["06:00", "07:00"]) == [15.0, 0.0]


def test_perfectly_repeating_days_have_zero_error():
    slots = {f"{h:02d}:{m:02d}": float(h) for h in range(24) for m in (0, 30)}
    series = make_series(5, slots)
    result = forecast.evaluate(series)
    assert result["mae_kw"] == 0.0


def test_evaluate_needs_enough_history():
    with pytest.raises(ValueError):
        forecast.evaluate([("2026-10-01T06:00:00+00:00", 1.0)])
