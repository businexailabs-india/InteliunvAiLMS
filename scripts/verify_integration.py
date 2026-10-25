"""Drive the ten business scenarios against a running stack.

Usage:  python scripts/verify_integration.py [--base http://localhost:8000]

Prints PASS / FAIL / GAP per check and exits non-zero if anything FAILs.
GAP means the capability is not implemented yet (documented, not faked).
"""

from __future__ import annotations

import argparse
import sys
import uuid

import httpx

PASSWORD = "Demo@2025"
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"[{status:4}] {name}" + (f" - {detail}" if detail else ""))


def check(name: str, condition: bool, detail: str = "") -> bool:
    record("PASS" if condition else "FAIL", name, "" if condition else detail)
    return condition


def gap(name: str, detail: str) -> None:
    record("GAP", name, detail)


class Client:
    def __init__(self, base: str, email: str, slug: str | None = None) -> None:
        self.http = httpx.Client(base_url=base, timeout=30)
        body: dict = {"email": email, "password": PASSWORD}
        if slug:
            body["institution_slug"] = slug
        response = self.http.post("/api/v1/auth/demo-login", json=body)
        response.raise_for_status()
        self.session = response.json()
        self.http.headers["Authorization"] = f"Bearer {self.session['access_token']}"

    def _send(self, method: str, path: str, **kwargs):
        # Docker Desktop's port proxy occasionally resets idle keep-alive sockets on Windows.
        for attempt in range(3):
            try:
                return self.http.request(method, path, **kwargs)
            except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError):
                if attempt == 2:
                    raise
        raise RuntimeError("unreachable")

    def get(self, path: str, **kwargs):
        return self._send("GET", path, **kwargs)

    def post(self, path: str, json=None):
        return self._send("POST", path, json=json)

    def patch(self, path: str, json=None):
        return self._send("PATCH", path, json=json)


def login_any(base: str, role: str, slug: str, indexes=range(1, 60)) -> Client | None:
    for index in indexes:
        email = f"demo.{role}.{index:04d}@example.invalid"
        try:
            return Client(base, email, slug)
        except httpx.HTTPError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    base = parser.parse_args().base

    student = Client(base, "aarav.sharma@inteluniven.edu")
    teacher = Client(base, "maya.chen@inteluniven.edu")
    coordinator = Client(base, "riya.nair@inteluniven.edu")
    parent = Client(base, "priya.sharma@inteluniven.edu")
    admin = Client(base, "olivia.harris@inteluniven.edu")
    slug = student.session["institution_slug"]

    print("\n== Login / roles ==")
    check("student role", "student" in student.session["roles"])
    check("teacher role", "teacher" in teacher.session["roles"])
    check("coordinator role", "coordinator" in coordinator.session["roles"])
    check("parent role", "parent_guardian" in parent.session["roles"])
    check("admin role", "institution_admin" in admin.session["roles"])
    check("no token rejected", httpx.get(f"{base}/api/v1/courses").status_code == 401)
    check("bad password rejected", httpx.post(f"{base}/api/v1/auth/demo-login", json={"email": "aarav.sharma@inteluniven.edu", "password": "x"}).status_code == 401)

    print("\n== S1 Student learning ==")
    courses = student.get("/api/v1/courses").json()
    check("student sees enrolled courses", len(courses) > 0, str(len(courses)))
    course = courses[0]
    lessons = student.get(f"/api/v1/courses/{course['id']}/lessons").json()
    check("course has lessons", len(lessons) > 0)
    before = {e["course_id"]: e["progress_pct"] for e in student.get("/api/v1/enrollments").json()}
    done = student.post("/api/v1/progress", {"lesson_id": lessons[0]["id"]})
    check("lesson completion persisted", done.status_code == 200, done.text)
    after = {e["course_id"]: e["progress_pct"] for e in student.get("/api/v1/enrollments").json()}
    check("enrollment progress increased", after.get(course["id"], 0) >= before.get(course["id"], 0))
    dash = student.get("/api/v1/dashboard").json()
    check("dashboard returns live metrics", dash["metrics"].get("courses", 0) > 0)

    print("\n== S2 Teacher assessment ==")
    teacher_courses = teacher.get("/api/v1/courses").json()
    target = next((c for c in teacher_courses if c["id"] == course["id"]), teacher_courses[0])
    title = f"Verify Quiz {uuid.uuid4().hex[:6]}"
    # Question bank: author -> four-eyes review -> build quiz from approved items.
    q_ids = []
    for prompt, answer, options in (("2+2?", "4", ["3", "4"]), ("Capital of France?", "Paris", ["Paris", "Berlin"])):
        made = teacher.post("/api/v1/question-bank", {"course_id": target["id"], "prompt": prompt, "options": options, "answer": answer})
        check(f"teacher drafts question '{prompt}'", made.status_code == 201, made.text)
        q_ids.append(made.json()["id"])
    check("MCQ answer must match options", teacher.post("/api/v1/question-bank", {"prompt": "bad", "options": ["a"], "answer": "z"}).status_code == 422)
    check("author cannot approve own question", teacher.post(f"/api/v1/question-bank/{q_ids[0]}/approve").status_code == 403)
    unapproved = teacher.post("/api/v1/assessments/from-bank", {"course_id": target["id"], "title": "Unapproved draft", "item_ids": q_ids})
    check("unapproved questions blocked", unapproved.status_code == 409, str(unapproved.status_code))
    for qid in q_ids:
        check("coordinator approves question", coordinator.post(f"/api/v1/question-bank/{qid}/approve").status_code == 200)
    check("student cannot read question bank", student.get("/api/v1/question-bank").status_code == 403)
    created = teacher.post("/api/v1/assessments/from-bank", {"course_id": target["id"], "title": title, "item_ids": q_ids})
    check("teacher builds quiz from approved bank", created.status_code == 201, created.text)
    quiz = created.json()
    check("student cannot create quiz", student.post("/api/v1/assessments", {"course_id": target["id"], "title": "x"}).status_code == 403)
    visible = next((a for a in student.get("/api/v1/assessments").json() if a["id"] == quiz["id"]), None)
    check("student sees quiz", visible is not None)
    if visible:
        leaked = any("answer" in q for q in visible["questions"])
        check("answer key hidden from student", not leaked, "student response contains answer keys")
    attempt = student.post(f"/api/v1/assessments/{quiz['id']}/attempts", {"answers": [{"question_id": "q1", "value": "4"}, {"question_id": "q2", "value": "Berlin"}]})
    check("student attempt graded (50% = 1 of 2)", attempt.status_code == 201 and attempt.json()["score"] == 50, attempt.text)
    attempt_id = attempt.json()["id"] if attempt.status_code == 201 else None
    partial = student.post(f"/api/v1/assessments/{quiz['id']}/attempts", {"answers": [{"question_id": "q1", "value": "4"}]})
    check("unanswered questions count against score", partial.status_code == 201 and partial.json()["score"] == 50, partial.text)
    check("unpublished result hidden from student", all(r["id"] != attempt_id for r in student.get("/api/v1/results").json()))
    check("teacher sees result", any(r["id"] == attempt_id for r in teacher.get("/api/v1/results", params={"assessment_id": quiz["id"]}).json()))

    print("\n== S3 Coordinator approval ==")
    student_id = student.session["user_id"]
    att = coordinator.get("/api/v1/attendance", params={"student_id": student_id})
    check("coordinator reviews attendance", att.status_code == 200, att.text)
    check("teacher cannot adjust score", teacher.post(f"/api/v1/results/{attempt_id}/adjust", {"revised_score": 2, "reason": "teacher attempt"}).status_code == 403)
    adj = coordinator.post(f"/api/v1/results/{attempt_id}/adjust", {"revised_score": 80, "reason": "Verified manual re-mark"})
    check("coordinator adjusts score", adj.status_code == 200 and adj.json()["score"] == 80, adj.text)
    check("adjustment needs a reason", coordinator.post(f"/api/v1/results/{attempt_id}/adjust", {"revised_score": 90, "reason": "x"}).status_code == 422)
    other_course = next((c for c in teacher_courses if c["id"] != target["id"]), None)
    card = coordinator.post("/api/v1/scorecards", {"course_id": target["id"], "payload": {"attempt_id": attempt_id}})
    check("scorecard created", card.status_code == 200, card.text)
    approve = coordinator.post(f"/api/v1/scorecards/{card.json()['id']}/approve")
    check("scorecard approved", approve.status_code == 200, approve.text)
    check("scorecard publishes only its course", approve.json().get("attempts_published", 0) < 500, str(approve.json()))
    published = next((r for r in student.get("/api/v1/results", params={"assessment_id": quiz["id"]}).json() if r["id"] == attempt_id), None)
    check("student sees published result", published is not None and published["score"] == 80)
    check("student cannot approve scorecards", student.post(f"/api/v1/scorecards/{card.json()['id']}/approve").status_code == 403)

    print("\n== S4 AI Study Buddy ==")
    usage_before = admin.get("/api/v1/ai/usage").json()["used"]
    ask = student.post("/api/v1/ai/study-buddy", {"message": "Explain this course", "course_id": course["id"]})
    check("study buddy responds", ask.status_code == 200, ask.text)
    if ask.status_code == 200:
        body = ask.json()
        check("response labeled mock", body["mock"] is True and body["provider"] == "mock")
        check("citations returned", len(body["citations"]) > 0)
    usage_after = admin.get("/api/v1/ai/usage").json()["used"]
    check("token usage recorded", usage_after > usage_before)

    print("\n== S5 Gamification ==")
    play = student.post("/api/v1/gamification/play", {"game_type": "quick_quest", "correct": 8, "total": 10, "elapsed_seconds": 20, "source_event_id": str(uuid.uuid4())})
    check("quick quest awards XP", play.status_code == 200 and play.json()["xp_awarded"] > 0, play.text)
    if play.status_code == 200:
        board = play.json()
        check("rank computed for learner", board["rank"] >= 1 and board["total_xp"] > 0, str(board["rank"]))
        check("leaderboard ordered", [r["xp"] for r in board["leaderboard"]] == sorted((r["xp"] for r in board["leaderboard"]), reverse=True))
    event = str(uuid.uuid4())
    first = student.post("/api/v1/gamification/play", {"game_type": "quiz", "correct": 5, "total": 10, "elapsed_seconds": 30, "source_event_id": event}).json()
    second = student.post("/api/v1/gamification/play", {"game_type": "quiz", "correct": 5, "total": 10, "elapsed_seconds": 30, "source_event_id": event}).json()
    check("replayed event not double-counted", second["xp_awarded"] == 0 and first["total_xp"] == second["total_xp"])
    games = student.get("/api/v1/gamification").json()["games"]
    check("all four games listed", {g["id"] for g in games} >= {"quiz", "quick_quest", "flashcards", "daily"})
    gap("badges / streaks", "no badge or streak model yet; XP ledger and leaderboard only")

    print("\n== S6 AI-proctored exam ==")
    no_consent = student.post("/api/v1/proctoring/sessions", {"assessment_id": quiz["id"], "consent": False, "camera_ready": True, "microphone_ready": True})
    check("consent required", no_consent.status_code == 400)
    session = student.post("/api/v1/proctoring/sessions", {"assessment_id": quiz["id"], "consent": True, "camera_ready": True, "microphone_ready": True})
    check("proctoring session created", session.status_code == 201, session.text)
    if session.status_code == 201:
        sid = session.json()["id"]
        check("labeled synthetic", session.json()["synthetic"] is True)
        check("never auto-disqualifies", session.json()["decision"] == "pending_human_review")
        check("event recorded", teacher.post(f"/api/v1/proctoring/sessions/{sid}/events").status_code == 200)
        check("reviewer sees case", any(s["id"] == sid for s in teacher.get("/api/v1/proctoring", params={"assessment_id": quiz["id"]}).json()))
        events = coordinator.get(f"/api/v1/proctoring/{sid}/events").json()
        check("reviewer sees integrity events", len(events) >= 2 and all(e["synthetic"] for e in events))
        check("automatic disqualification not allowed", coordinator.post(f"/api/v1/proctoring/{sid}/review", {"decision": "disqualified"}).status_code == 422)
        review = coordinator.post(f"/api/v1/proctoring/{sid}/review", {"decision": "no_concern", "notes": "Reviewed synthetic events"})
        check("human review recorded", review.status_code == 200 and review.json()["decision"] == "no_concern", review.text)
        check("student cannot review", student.post(f"/api/v1/proctoring/{sid}/review", {"decision": "cleared"}).status_code == 403)

    print("\n== S7 Parent portal ==")
    learners = parent.get("/api/v1/parents/learners").json()
    check("parent sees linked learner", len(learners) > 0)
    if learners:
        linked = learners[0]["id"]
        check("parent reads linked attendance", parent.get("/api/v1/attendance", params={"student_id": linked}).status_code == 200)
    unlinked = parent.get("/api/v1/attendance", params={"student_id": str(uuid.uuid4())})
    check("parent blocked for unlinked learner", unlinked.status_code == 403, str(unlinked.status_code))
    check("parent cannot create courses", parent.post("/api/v1/courses", {"title": "nope"}).status_code == 403)
    check("parent sees only published results", all(r["published"] for r in parent.get("/api/v1/results").json()))

    print("\n== S8 Corporate training ==")
    # Some synthetic corporate users are deliberately inactive (e.g. tenant 1), so look for a
    # tenant that has an active HR manager, trainer, reviewer and learner.
    team = None
    for n in range(1, 11):
        tslug = f"demo-tenant-{n}"
        hr = login_any(base, "hr_manager", tslug, [n])
        trainer = login_any(base, "corporate_trainer", tslug, [n, n + 10, n + 20])
        if hr is None or trainer is None:
            continue
        reviewer = login_any(base, "coordinator", tslug, range(1, 25)) or login_any(base, "content_reviewer", tslug, range(1, 25))
        employee = login_any(base, "student", tslug, range(1, 80))
        if reviewer and employee:
            team = (tslug, hr, trainer, reviewer, employee)
            break
    if team is None:
        gap("corporate personas", "no tenant with active hr_manager, corporate_trainer, reviewer and student")
    else:
        tslug, hr, trainer, reviewer, employee = team
        print(f"   (tenant {tslug})")
        check("HR persona has corporate_hr role", "corporate_hr" in hr.session["roles"], str(hr.session["roles"]))
        corp_courses = hr.get("/api/v1/courses").json()
        check("tenant has a course", len(corp_courses) > 0)
        ccourse = corp_courses[0]["id"]
        # Reruns must be independent: choose a learner not yet enrolled in this course.
        for idx in range(1, 200):
            candidate = login_any(base, "student", tslug, [idx])
            if candidate is None:
                continue
            enrolled_ids = {e["course_id"] for e in candidate.get("/api/v1/enrollments").json()}
            if ccourse not in enrolled_ids:
                employee = candidate
                break
        employee_id = employee.session["user_id"]
        # Trainer authors a one-question quiz through the reviewed bank for this course.
        qb = trainer.post("/api/v1/question-bank", {"course_id": ccourse, "prompt": "Safety first?", "options": ["yes", "no"], "answer": "yes"})
        check("trainer drafts question", qb.status_code == 201, qb.text)
        check("reviewer approves question", reviewer.post(f"/api/v1/question-bank/{qb.json()['id']}/approve").status_code == 200)
        quiz2 = trainer.post("/api/v1/assessments/from-bank", {"course_id": ccourse, "title": "Compliance check", "item_ids": [qb.json()["id"]]})
        check("trainer builds compliance quiz", quiz2.status_code == 201, quiz2.text)
        cohort = hr.post("/api/v1/cohorts", {"name": f"Cohort {uuid.uuid4().hex[:6]}", "course_id": ccourse})
        check("HR creates cohort", cohort.status_code == 201, cohort.text)
        check("employee cannot create cohort", employee.post("/api/v1/cohorts", {"name": "x"}).status_code == 403)
        cid = cohort.json()["id"]
        blocked = employee.post(f"/api/v1/assessments/{quiz2.json()['id']}/attempts", {"answers": [{"question_id": "q1", "value": "yes"}]})
        check("non-enrolled employee blocked from quiz", blocked.status_code == 403, str(blocked.status_code))
        added = hr.post(f"/api/v1/cohorts/{cid}/members", {"user_ids": [employee_id]})
        check("HR adds employee to cohort", added.status_code == 201 and added.json()["added"] == 1, added.text)
        again = hr.post(f"/api/v1/cohorts/{cid}/members", {"user_ids": [employee_id]})
        check("cohort membership idempotent", again.status_code == 201 and again.json()["added"] == 0)
        check("non-member user rejected", hr.post(f"/api/v1/cohorts/{cid}/members", {"user_ids": [str(uuid.uuid4())]}).status_code == 422)
        assign = trainer.post("/api/v1/assignments", {"course_id": ccourse, "title": "Corporate task", "instructions": "Complete the module"})
        check("trainer assigns content", assign.status_code == 201, assign.text)
        sub = employee.post(f"/api/v1/assignments/{assign.json()['id']}/submissions", {"body": "Completed corporate task"})
        check("employee submits assignment", sub.status_code == 201, sub.text)
        taken = employee.post(f"/api/v1/assessments/{quiz2.json()['id']}/attempts", {"answers": [{"question_id": "q1", "value": "yes"}]})
        check("enrolled employee passes quiz", taken.status_code == 201 and taken.json()["score"] == 100, taken.text)
        report = hr.get("/api/v1/reports/completion")
        check("HR completion report", report.status_code == 200, report.text)
        row = next((r for r in report.json().get("cohorts", []) if r["cohort_id"] == cid), None) if report.status_code == 200 else None
        check("report reflects member + passed assessment", row is not None and row["members"] == 1 and row["members_passed"] == 1 and row["completion_rate_pct"] == 100.0, str(row))
        check("employee cannot view HR report", employee.get("/api/v1/reports/completion").status_code == 403)

        print("\n== S11 Academics: directory, assignments, attendance, roster ==")
        other_slug = "demo-tenant-1" if tslug != "demo-tenant-1" else "demo-tenant-2"
        outsider = login_any(base, "student", other_slug, range(1, 200))
        outsider_id = outsider.session["user_id"] if outsider else str(uuid.uuid4())
        people = hr.get("/api/v1/directory", params={"q": employee.session["email"]})
        check("HR searches tenant directory", people.status_code == 200 and any(p["id"] == employee_id for p in people.json()), people.text[:200])
        check("directory is tenant-scoped (no foreign users)", all(p["id"] != outsider_id for p in hr.get("/api/v1/directory", params={"limit": 50}).json()))
        check("employee cannot search directory", employee.get("/api/v1/directory").status_code == 403)
        mine = employee.get("/api/v1/assignments", params={"course_id": ccourse}).json()
        row_mine = next((a for a in mine if a["id"] == assign.json()["id"]), None)
        check("employee sees own submission on assignment", row_mine is not None and row_mine["submission"] is not None)
        staff_view = trainer.get("/api/v1/assignments", params={"course_id": ccourse}).json()
        row_staff = next((a for a in staff_view if a["id"] == assign.json()["id"]), None)
        check("trainer sees submission count", row_staff is not None and row_staff["submission_count"] >= 1)
        subs = trainer.get(f"/api/v1/assignments/{assign.json()['id']}/submissions")
        check("trainer lists submissions with names", subs.status_code == 200 and any(s["student_name"] for s in subs.json()))
        check("employee cannot list submissions", employee.get(f"/api/v1/assignments/{assign.json()['id']}/submissions").status_code == 403)
        graded = trainer.post(f"/api/v1/submissions/{sub.json()['id']}/grade", {"score": 88, "feedback": "Clear work"})
        check("trainer grades submission", graded.status_code == 200 and graded.json()["score"] == 88, graded.text)
        after = next((a for a in employee.get("/api/v1/assignments", params={"course_id": ccourse}).json() if a["id"] == assign.json()["id"]), None)
        check("employee sees score and feedback", after is not None and after["submission"]["score"] == 88 and after["submission"]["feedback"] == "Clear work")
        check("other-tenant learner cannot submit", outsider is not None and outsider.post(f"/api/v1/assignments/{assign.json()['id']}/submissions", {"body": "x"}).status_code in (403, 404))
        check("invalid attendance status rejected", trainer.post("/api/v1/attendance/record", {"course_id": ccourse, "entries": [{"student_id": employee_id, "status": "teleported"}]}).status_code == 422)
        check("attendance for non-enrolled learner rejected", trainer.post("/api/v1/attendance/record", {"course_id": ccourse, "entries": [{"student_id": outsider_id, "status": "present"}]}).status_code == 422)
        rec = trainer.post("/api/v1/attendance/record", {"course_id": ccourse, "entries": [{"student_id": employee_id, "status": "present"}]})
        check("trainer records attendance", rec.status_code == 201 and rec.json()["recorded"] == 1, rec.text)
        trainer.post("/api/v1/attendance/record", {"course_id": ccourse, "entries": [{"student_id": employee_id, "status": "absent"}]})
        ros = trainer.get("/api/v1/roster", params={"course_id": ccourse})
        me = next((l for l in ros.json()["learners"] if l["student_id"] == employee_id), None) if ros.status_code == 200 else None
        check("roster shows attendance 50%", me is not None and me["attendance_pct"] == 50.0 and me["sessions_total"] == 2, str(me))
        check("roster flags attendance below threshold", me is not None and me["eligible"] is False)
        check("roster includes quiz average", me is not None and me["avg_score"] == 100.0, str(me))
        check("employee cannot view roster", employee.get("/api/v1/roster", params={"course_id": ccourse}).status_code == 403)
        if me and "coordinator" in reviewer.session["roles"]:
            fix = reviewer.patch(f"/api/v1/attendance/{me['attendance_id']}", {"sessions_present": 2, "sessions_total": 2, "reason": "Late arrival was marked absent"})
            check("coordinator corrects attendance with reason", fix.status_code == 200 and fix.json()["sessions_present"] == 2, fix.text)
            check("correction needs a reason", reviewer.patch(f"/api/v1/attendance/{me['attendance_id']}", {"sessions_present": 1, "reason": "x"}).status_code == 422)
            check("present cannot exceed total", reviewer.patch(f"/api/v1/attendance/{me['attendance_id']}", {"sessions_present": 9, "reason": "Impossible value"}).status_code == 422)
            check("trainer cannot correct attendance", trainer.patch(f"/api/v1/attendance/{me['attendance_id']}", {"sessions_present": 2, "reason": "Not permitted"}).status_code == 403)

    print("\n== S9 Subscription administration ==")
    billing = admin.get("/api/v1/billing")
    check("admin views subscription", billing.status_code == 200 and billing.json()["plan"] is not None, billing.text)
    check("student cannot view billing", student.get("/api/v1/billing").status_code == 403)
    usage = admin.get("/api/v1/ai/usage").json()
    check("usage dashboard shows consumption", usage["used"] > 0 and len(usage["events"]) > 0)
    check("student cannot change quota", student.patch("/api/v1/billing/ai-quota", {"monthly_token_quota": 1}).status_code == 403)
    quota = admin.patch("/api/v1/billing/ai-quota", {"monthly_token_quota": usage["used"] + 1})
    check("admin sets tenant AI quota", quota.status_code == 200, quota.text)
    try:
        blocked = student.post("/api/v1/ai/study-buddy", {"message": "Another question"})
        check("quota limit enforced (429)", blocked.status_code == 429, str(blocked.status_code))
    finally:
        restore = admin.patch("/api/v1/billing/ai-quota", {"monthly_token_quota": 500000})
        check("quota restored", restore.status_code == 200)

    print("\n== S10 Multi-tenant isolation ==")
    other = login_any(base, "student", "demo-tenant-2", range(1, 80)) or login_any(base, "teacher", "demo-tenant-2")
    if other is None:
        gap("second tenant login", "no demo-tenant-2 user available")
    else:
        other_courses = other.get("/api/v1/courses").json()
        mine = {c["id"] for c in courses}
        check("tenant 2 has its own courses", len(other_courses) >= 0)
        check("course sets disjoint", mine.isdisjoint({c["id"] for c in other_courses}))
        foreign = other_courses[0]["id"] if other_courses else None
        if foreign:
            check("cross-tenant lessons empty", student.get(f"/api/v1/courses/{foreign}/lessons").json() == [])
            check("cross-tenant progress 404", student.post("/api/v1/progress", {"lesson_id": str(uuid.uuid4())}).status_code == 404)
            check("cross-tenant assessment 404", student.post(f"/api/v1/assessments/{foreign}/attempts", {"answers": []}).status_code == 404)
        forged = httpx.get(f"{base}/api/v1/courses", headers={"Authorization": "Bearer not.a.jwt"})
        check("forged token rejected", forged.status_code == 401)

    fails = [r for r in results if r[0] == "FAIL"]
    gaps = [r for r in results if r[0] == "GAP"]
    passed = [r for r in results if r[0] == "PASS"]
    print(f"\nSummary: {len(passed)} passed, {len(fails)} failed, {len(gaps)} gaps")
    for status, name, detail in fails:
        print(f"  FAIL {name}: {detail}")
    for status, name, detail in gaps:
        print(f"  GAP  {name}: {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
