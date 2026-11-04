"""Tests for sorting and preselecting sensors by zone."""

from custom_components.readi.catalog import Candidate, Zone, nearest_zone, preselect, sort_candidates

HOME = Zone("Home", 48.9400, 8.4000, 100)
WORK = Zone("Work", 48.9300, 8.3800, 100)
STUTTGART = Zone("Stuttgart", 48.7758, 9.1829, 100)


def _c(cid, kind, lat=None, lon=None, name=None):
    return Candidate(cid, kind, name or cid, lat, lon)


def test_nearest_zone_measures_from_the_zone_edge():
    sensor = _c("t1", "temperature", 48.9400, 8.4100)  # ~730 m east of Home

    zone, km = nearest_zone(sensor, [HOME, WORK])

    assert zone == "Home"
    assert 0.6 < km < 0.65  # ~0.73 km minus the 100 m radius


def test_nearest_zone_without_coordinates():
    assert nearest_zone(_c("w1", "weather"), [HOME]) is None


def test_nearest_zone_without_zones():
    assert nearest_zone(_c("t1", "temperature", 48.94, 8.40), []) is None


def test_preselect_picks_nearest_of_each_kind_per_zone():
    candidates = [
        _c("t_home", "temperature", 48.9401, 8.4001),
        _c("t_far", "temperature", 48.9500, 8.4200),
        _c("t_work", "temperature", 48.9301, 8.3801),
        _c("traffic_home", "traffic", 48.9410, 8.4010),
    ]

    assert preselect(candidates, [HOME, WORK]) == {"t_home", "t_work", "traffic_home"}


def test_preselect_merges_shared_nearest_sensor():
    candidates = [_c("w1", "weather", 48.9350, 8.3900)]

    assert preselect(candidates, [HOME, WORK]) == {"w1"}


def test_preselect_ignores_zones_far_away():
    candidates = [_c("t1", "temperature", 48.94, 8.40)]

    assert preselect(candidates, [STUTTGART]) == set()


def test_preselect_skips_sensors_without_coordinates():
    assert preselect([_c("w1", "weather")], [HOME]) == set()


def test_sort_candidates_by_distance_then_unlocated_by_name():
    candidates = [
        _c("b", "weather", name="Schlauchturm"),
        _c("far", "temperature", 48.9500, 8.4200),
        _c("a", "weather", name="Oberweier"),
        _c("near", "temperature", 48.9401, 8.4001),
    ]

    ordered = [c.id for c in sort_candidates(candidates, [HOME])]

    assert ordered == ["near", "far", "a", "b"]
