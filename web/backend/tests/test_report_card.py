"""Отчёт по нарушениям карточкой: сводка полями, уровни/топ/страны таблицами."""
import json
from datetime import datetime, timezone

from shared.violation_reports import ReportType, ViolationReportData, ViolationReportService, report_from_row

START = datetime(2026, 10, 8, tzinfo=timezone.utc)
END = datetime(2026, 10, 9, tzinfo=timezone.utc)


def _report(**over) -> ViolationReportData:
    data = dict(
        report_type=ReportType.DAILY, period_start=START, period_end=END,
        total_violations=40, critical_count=10, warning_count=20, monitor_count=10, unique_users=25,
        avg_score=61.5, max_score=97.0, prev_total_violations=32, trend_percent=25.0, trend_direction="up",
        top_violators=[{"username": "alex", "violations_count": 7, "max_score": 97.4},
                       {"username": "<b>evil</b>", "violations_count": 3, "max_score": 80.0}],
        by_country={"RU": 30, "DE": 10}, by_action={"temp_block": 12, "monitor": 28},
        by_asn_type={"mobile": 22, "datacenter": 18},
    )
    data.update(over)
    return ViolationReportData(**data)


def _tables(card):
    return [blk for blk in card.to_blocks() if blk["type"] == "table"]


def test_report_is_tables_not_lines():
    card = ViolationReportService().build_card(_report())
    blocks = card.to_blocks()
    assert blocks[0] == {"type": "heading", "text": "📊 Ежедневный отчёт по нарушениям", "size": 3}
    severity = next(t for t in _tables(card) if t["cells"][0][0]["text"] == "Уровень")
    assert [row[2]["text"] for row in severity["cells"][1:]] == ["25%", "50%", "25%"]
    top = next(t for t in _tables(card) if t["cells"][0][0]["text"] == "#")
    assert top["cells"][1][1]["text"] == {"type": "button", "button": {"text": "alex", "copy_text": {"text": "alex"}}}
    assert top["cells"][1][3]["text"] == "97"
    countries = next(t for t in _tables(card) if t["cells"][0][0]["text"] == "Страна")
    assert countries["cells"][1][0]["text"] == "🇷🇺 RU"
    details = next(blk for blk in blocks if blk["type"] == "details")
    assert details["summary"] == "🔌 Провайдеры и действия"


def test_trend_and_html_view():
    html = ViolationReportService().build_card(_report()).to_html()
    assert "Тренд: 📈 +25.0% · было 32" in html
    assert "&lt;b&gt;evil&lt;/b&gt;" in html and "<b>evil</b>" not in html


def test_empty_period_says_so():
    card = ViolationReportService().build_card(_report(total_violations=0, critical_count=0, warning_count=0,
                                                       monitor_count=0, top_violators=[], by_country={}))
    assert "Нарушений за период нет" in card.to_html()
    assert len(_tables(card)) == 1  # только сводка


def test_saved_report_is_rebuilt_from_its_numbers():
    """Пересылка из панели — та же карточка, что ушла по расписанию."""
    report = _report()
    row = {
        "id": 5, "report_type": "daily", "period_start": START, "period_end": END,
        "total_violations": 40, "critical_count": 10, "warning_count": 20, "monitor_count": 10,
        "unique_users": 25, "prev_total_violations": 32, "trend_percent": 25.0,
        "top_violators": json.dumps(report.top_violators), "by_country": json.dumps(report.by_country),
        "by_action": report.by_action, "by_asn_type": None, "message_text": "old",
    }
    rebuilt = report_from_row(row)
    assert rebuilt.top_violators == report.top_violators and rebuilt.by_asn_type == {}
    service = ViolationReportService()
    assert _tables(service.build_card(rebuilt))[2] == _tables(service.build_card(report))[2]
