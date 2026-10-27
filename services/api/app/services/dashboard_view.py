"""Shape dashboard panels from records that were already loaded."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

TEACHING_NOTE_KINDS = frozenset({"lesson_plan", "quiz", "rubric", "insight", "support"})
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _zone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return UTC


def week_activity(counts: dict[date, int], today: date) -> list[dict]:
    start = today - timedelta(days=6)
    rows = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        rows.append({"date": day.isoformat(), "label": WEEKDAYS[day.weekday()], "completions": int(counts.get(day, 0))})
    return rows


def format_class(title: str, course: str, starts_at: datetime, timezone_name: str, now: datetime) -> dict:
    zone = _zone(timezone_name or "UTC")
    local = starts_at.astimezone(zone)
    current = now.astimezone(zone)
    return {
        "title": title,
        "course": course,
        "when": f"{WEEKDAYS[local.weekday()]} {local.day:02d} {MONTHS[local.month - 1]} · {local.strftime('%H:%M')}",
        "today": local.date() == current.date(),
    }


def build_alerts(
    *,
    notifications: list[dict],
    at_risk: int,
    pending_scorecards: int,
    ungraded: int,
    staff: bool,
) -> list[dict]:
    alerts: list[dict] = []
    for item in notifications:
        if item.get("read"):
            continue
        alerts.append(
            {
                "title": item.get("title") or "Notification",
                "detail": item.get("body") or "Unread notification",
                "module": "Communication",
                "sub": "",
            }
        )
    if staff and at_risk:
        alerts.append(
            {
                "title": "Attendance below 75%",
                "detail": f"{at_risk} attendance records",
                "module": "Attendance",
                "sub": "",
            }
        )
    if staff and pending_scorecards:
        alerts.append(
            {
                "title": "Scorecards waiting for approval",
                "detail": f"{pending_scorecards} scorecards",
                "module": "Assessments",
                "sub": "Results",
            }
        )
    if staff and ungraded:
        alerts.append(
            {
                "title": "Submissions without a score",
                "detail": f"{ungraded} submissions",
                "module": "Assignments",
                "sub": "",
            }
        )
    return alerts[:5]


def cohort_overview(rows: list[dict]) -> list[dict]:
    overview = []
    for row in rows:
        members = int(row.get("members") or 0)
        if row.get("course_id"):
            attendance = row.get("attendance_pct")
            progress = row.get("progress_pct")
            signal = f"{0 if attendance is None else attendance}% attendance"
            status = f"{members} learners · {0 if progress is None else progress}% progress"
        else:
            signal = "No course linked"
            status = f"{members} learners"
        overview.append({"name": row["name"], "signal": signal, "status": status})
    return overview
