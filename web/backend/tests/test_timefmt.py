"""Единое время для людей: shared.timefmt."""
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from shared import timefmt


@pytest.fixture()
def tz():
    """Подменить настройку display_timezone."""
    def use(name):
        return patch.object(timefmt, "zone_name", return_value=name)
    return use


MOMENT = datetime(2026, 9, 23, 21, 30, tzinfo=timezone.utc)


class TestFormat:
    def test_moscow_is_default_and_labelled(self, tz):
        with tz("Europe/Moscow"):
            assert timefmt.fmt(MOMENT) == "24.09.2026 00:30 МСК"

    def test_naive_time_is_utc(self, tz):
        with tz("Europe/Moscow"):
            assert timefmt.fmt(datetime(2026, 9, 23, 21, 30)) == "24.09.2026 00:30 МСК"

    def test_iso_strings_from_the_panel(self, tz):
        with tz("Europe/Moscow"):
            assert timefmt.fmt("2026-09-23T21:30:00.000Z", "%H:%M") == "00:30 МСК"

    def test_other_zone_gets_an_offset_label(self, tz):
        with tz("Asia/Yekaterinburg"):
            assert timefmt.fmt(MOMENT, "%H:%M") == "02:30 UTC+5"

    def test_half_hour_offset(self, tz):
        with tz("Asia/Kolkata"):
            assert timefmt.fmt(MOMENT, "%H:%M") == "03:00 UTC+5:30"

    def test_utc(self, tz):
        with tz("UTC"):
            assert timefmt.fmt(MOMENT, "%H:%M") == "21:30 UTC"

    def test_unknown_zone_falls_back_to_utc_honestly(self, tz):
        with tz("Mars/Olympus"):
            assert timefmt.fmt(MOMENT, "%H:%M") == "21:30 UTC"

    def test_without_label(self, tz):
        with tz("Europe/Moscow"):
            assert timefmt.fmt(MOMENT, "%H:%M", with_label=False) == "00:30"

    @pytest.mark.parametrize("value,expected", [(None, ""), ("", ""), ("не дата", "не дата")])
    def test_empty_and_garbage(self, tz, value, expected):
        with tz("Europe/Moscow"):
            assert timefmt.fmt(value) == expected

    def test_plain_date_is_not_shifted(self, tz):
        with tz("Asia/Tokyo"):
            assert timefmt.fmt_date(date(2026, 9, 23)) == "23.09.2026"

    def test_datetime_date_follows_the_zone(self, tz):
        with tz("Europe/Moscow"):
            assert timefmt.fmt_date(MOMENT) == "24.09.2026"


def test_settings_unavailable_means_default_zone():
    with patch("shared.config_service.config_service.get", side_effect=RuntimeError("no db")):
        assert timefmt.zone_name() == timefmt.DEFAULT_TIMEZONE


def test_report_day_bounds_follow_the_zone(tz):
    """«Вчера» у админа в Москве — с полуночи до полуночи по Москве."""
    from shared.violation_reports import ReportType, ViolationReportService

    with tz("Europe/Moscow"):
        start, end = ViolationReportService()._get_period_bounds(ReportType.DAILY, MOMENT)
        assert timefmt.fmt_date(start) == "23.09.2026"
    assert start.astimezone(timezone.utc) == datetime(2026, 9, 22, 21, 0, tzinfo=timezone.utc)
    assert end.astimezone(timezone.utc) == datetime(2026, 9, 23, 21, 0, tzinfo=timezone.utc)


class TestFilters:
    def test_bare_date_is_a_day_in_the_panel_zone(self, tz):
        with tz("Europe/Moscow"):
            assert timefmt.parse_filter("2026-09-23") == datetime(2026, 9, 22, 21, 0, tzinfo=timezone.utc)
            # конец диапазона — начало следующих суток: выбранный день целиком
            assert timefmt.parse_filter("2026-09-23", end=True) == datetime(2026, 9, 23, 21, 0, tzinfo=timezone.utc)

    def test_naive_time_is_on_panel_clock_and_explicit_zone_is_kept(self, tz):
        with tz("Europe/Moscow"):
            assert timefmt.parse_filter("2026-09-23T10:00") == datetime(2026, 9, 23, 7, 0, tzinfo=timezone.utc)
            assert timefmt.parse_filter("2026-09-23T10:00:00Z") == datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)

    def test_empty_and_garbage(self, tz):
        with tz("Europe/Moscow"):
            assert timefmt.parse_filter(None) is None
            assert timefmt.parse_filter("  ") is None
            with pytest.raises(ValueError):
                timefmt.parse_filter("вчера")

    def test_bad_bound_is_dropped_not_fatal(self, tz):
        with tz("Europe/Moscow"):
            since, until = timefmt.filter_bounds("вчера", "2026-09-23")
        assert since is None
        assert until == datetime(2026, 9, 23, 21, 0, tzinfo=timezone.utc)


class TestSqlZone:
    @pytest.mark.parametrize("name,expected", [
        ("Europe/Moscow", "'Europe/Moscow'"),
        ("UTC", "'UTC'"),
        ("Mars/Olympus", "'UTC'"),
        ("Europe/Moscow'; DROP TABLE users; --", "'UTC'"),
    ])
    def test_only_known_zones_reach_sql(self, tz, name, expected):
        with tz(name):
            assert timefmt.sql_zone() == expected
