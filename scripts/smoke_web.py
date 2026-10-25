"""Smoke-test the web tier: Vite compiles the live screens and /api proxies to FastAPI.

Usage: python scripts/smoke_web.py [--web http://localhost:8443]
"""

from __future__ import annotations

import argparse
import sys

import httpx

MODULES = ["/src/App.tsx", "/src/live/shared.tsx", "/src/live/LiveAcademics.tsx", "/src/live/LiveAdmin.tsx"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", default="http://localhost:8443")
    web = parser.parse_args().web
    failures = 0

    def report(ok: bool, label: str, detail: str = "") -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" - {detail}" if detail and not ok else ""))

    client = httpx.Client(timeout=60)
    for path in MODULES:
        response = client.get(web + path)
        report(response.status_code == 200 and "error" not in response.text[:200].lower(), f"vite serves {path}", str(response.status_code))

    login = client.post(web + "/api/v1/auth/demo-login", json={"email": "riya.nair@inteluniven.edu", "password": "Demo@2025"})
    report(login.status_code == 200, "login through proxy", login.text[:120])
    if login.status_code != 200:
        return 1
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    courses = client.get(web + "/api/v1/courses", headers=headers).json()
    report(bool(courses), "coordinator sees courses")
    course_id = courses[0]["id"]
    for path in (
        f"/api/v1/roster?course_id={course_id}",
        f"/api/v1/assessments?course_id={course_id}",
        f"/api/v1/assignments?course_id={course_id}",
        "/api/v1/proctoring",
        "/api/v1/attendance",
        "/api/v1/results",
    ):
        response = client.get(web + path, headers=headers)
        report(response.status_code == 200, f"GET {path.split('?')[0]} via proxy", f"{response.status_code} {response.text[:100]}")
    denied = client.get(web + "/api/v1/billing", headers=headers)
    report(denied.status_code == 403, "coordinator is denied billing (RBAC)", str(denied.status_code))
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
