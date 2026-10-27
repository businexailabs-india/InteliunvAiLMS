from datetime import UTC, date, datetime

from app.services.dashboard_view import build_alerts, cohort_overview, format_class, week_activity


def test_week_activity_uses_recorded_counts_only() -> None:
    today = date(2026, 10, 26)
    rows = week_activity({today: 2}, today)
    assert len(rows) == 7
    assert rows[-1] == {"date": "2026-10-26", "label": "Mon", "completions": 2}
    assert all(row["completions"] == 0 for row in rows[:-1])


def test_alerts_come_from_records_and_skip_read_notifications() -> None:
    alerts = build_alerts(
        notifications=[{"title": "Read already", "body": "old", "read": True}, {"title": "Parent message", "body": "Please call", "read": False}],
        at_risk=3,
        pending_scorecards=1,
        ungraded=4,
        staff=True,
    )
    titles = [item["title"] for item in alerts]
    assert titles == [
        "Parent message",
        "Attendance below 75%",
        "Scorecards waiting for approval",
        "Submissions without a score",
    ]
    assert "Security review" not in titles


def test_learner_alerts_do_not_include_staff_queues() -> None:
    alerts = build_alerts(
        notifications=[],
        at_risk=9,
        pending_scorecards=2,
        ungraded=6,
        staff=False,
    )
    assert alerts == []


def test_schedule_label_uses_the_class_timezone() -> None:
    starts = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
    now = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    row = format_class("Algebra", "Mathematics", starts, "UTC", now)
    assert row["when"] == "Mon 26 Oct · 09:00"
    assert row["today"] is True
    assert row["course"] == "Mathematics"


def test_cohort_overview_reports_missing_course_links() -> None:
    rows = cohort_overview(
        [
            {"name": "OA-24", "course_id": "course", "members": 12, "attendance_pct": 80.0, "progress_pct": 40},
            {"name": "Unlinked", "course_id": None, "members": 0, "attendance_pct": None, "progress_pct": None},
        ]
    )
    assert rows[0]["signal"] == "80.0% attendance"
    assert rows[0]["status"] == "12 learners · 40% progress"
    assert rows[1]["signal"] == "No course linked"
