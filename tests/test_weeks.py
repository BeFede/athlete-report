from datetime import date

import pytest

from athlete_report.weeks import (
    bootstrap_range,
    last_complete_week_start,
    mondays_between,
    week_end_for,
    week_start_for,
)


def test_week_start_is_monday():
    assert week_start_for(date(2026, 7, 3)) == date(2026, 6, 29)
    assert week_start_for(date(2026, 6, 29)) == date(2026, 6, 29)
    assert week_start_for(date(2026, 7, 5)) == date(2026, 6, 29)


def test_last_complete_week_mid_week():
    # viernes: la semana en curso no terminó
    assert last_complete_week_start(date(2026, 7, 3)) == date(2026, 6, 22)


def test_last_complete_week_on_monday():
    # lunes: la semana anterior terminó ayer
    assert last_complete_week_start(date(2026, 7, 6)) == date(2026, 6, 29)


def test_last_complete_week_on_sunday():
    # domingo en curso: la semana todavía no está completa
    assert last_complete_week_start(date(2026, 7, 5)) == date(2026, 6, 22)


def test_mondays_between_inclusive():
    weeks = mondays_between(date(2026, 4, 13), date(2026, 6, 29))
    assert weeks[0] == date(2026, 4, 13)
    assert weeks[-1] == date(2026, 6, 29)
    assert len(weeks) == 12


def test_mondays_between_rejects_non_monday():
    with pytest.raises(ValueError):
        mondays_between(date(2026, 4, 14), date(2026, 6, 29))


def test_bootstrap_range_12_weeks_140_days():
    data_start, data_end, weeks = bootstrap_range(12, date(2026, 7, 3), 56)
    assert len(weeks) == 12
    assert weeks[-1] == date(2026, 6, 22)
    assert weeks[0] == date(2026, 4, 6)
    assert data_end == week_end_for(weeks[-1])
    # history_weeks * 7 + 56 días de warm-up
    assert (data_end - data_start).days + 1 == 12 * 7 + 56 == 140
