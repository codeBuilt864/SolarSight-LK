from datetime import datetime, timezone

from solarsight import simulator


def utc(h, m=0):
    return datetime(2026, 10, 25, h, m, tzinfo=timezone.utc)


def test_no_solar_at_night():
    # 18:00 UTC is 23:30 in Sri Lanka
    assert simulator.clear_sky_factor(utc(18)) == 0.0


def test_solar_peaks_near_local_noon():
    noon_local = utc(6, 30)  # 12:00 in Sri Lanka
    morning_local = utc(1, 30)  # 07:00 in Sri Lanka
    assert simulator.clear_sky_factor(noon_local) > simulator.clear_sky_factor(morning_local)
    assert simulator.clear_sky_factor(noon_local) > 0.9


def test_power_never_exceeds_capacity():
    sites = simulator.make_sites()
    for site, ts, kw in simulator.generate(days=2, end=utc(12)):
        assert 0 <= kw <= site["capacity_kw"]


def test_generation_is_repeatable():
    a = [kw for _, _, kw in simulator.generate(days=1, seed=3, end=utc(12))]
    b = [kw for _, _, kw in simulator.generate(days=1, seed=3, end=utc(12))]
    assert a == b


def test_low_demand_day_is_lower_at_midday():
    assert simulator.demand_factor(utc(6, 30), True) < simulator.demand_factor(utc(6, 30), False)
