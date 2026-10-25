// Verifies the role -> sidebar module rules in src/access.ts.
// Run:  node scripts/check_access.mts      (Node 22.18+ runs TypeScript directly)
import { ALL_MODULES, allowListForBackendRoles, roleHidden, visibleModules, type Role } from "../src/access.ts";

let failures = 0;
function check(name: string, ok: boolean, detail = ""): void {
  if (!ok) failures += 1;
  console.log(`[${ok ? "PASS" : "FAIL"}] ${name}${ok || !detail ? "" : ` - ${detail}`}`);
}

const roles = Object.keys(roleHidden) as Role[];
const names = new Set<string>(ALL_MODULES);

check("30 modules defined, no duplicates", ALL_MODULES.length === 30 && names.size === 30);
for (const role of roles) {
  const unknown = roleHidden[role].filter((name) => !names.has(name));
  check(`${role}: hidden list only names real modules`, unknown.length === 0, unknown.join(", "));
}

const expectedCounts: Record<Role, number> = {
  Student: 18,
  "Teacher / Faculty": 25,
  "Training Coordinator": 10,
  "Parent / Guardian / HOD": 19,
  "Principal / L&D Lead": 23,
  Administrator: 30,
};
for (const role of roles) {
  const count = visibleModules(role).length;
  check(`${role}: ${expectedCounts[role]} modules visible`, count === expectedCounts[role], `got ${count}`);
}

// Every live (API-backed) screen must be reachable from the sidebar of the role it serves.
const liveScreens: [Role, string[]][] = [
  ["Student", ["Courses", "AI Study Buddy", "Assignments", "Assessments", "Gamification", "Attendance", "Gradebook"]],
  ["Teacher / Faculty", ["Assignments", "Assessments", "Attendance", "Gradebook"]],
  ["Training Coordinator", ["Assignments", "Assessments", "Attendance", "Student Information"]],
  ["Parent / Guardian / HOD", ["Attendance", "Gradebook"]],
  ["Principal / L&D Lead", ["Analytics"]],
  ["Administrator", ["Administration", "Analytics", "Assignments", "Attendance", "Gradebook"]],
];
for (const [role, modules] of liveScreens) {
  const visible = new Set(visibleModules(role));
  const missing = modules.filter((name) => !visible.has(name));
  check(`${role}: all live screens reachable`, missing.length === 0, `hidden: ${missing.join(", ")}`);
}

// Least privilege: sensitive modules stay away from learners, parents and coordinators.
for (const role of ["Student", "Parent / Guardian / HOD", "Training Coordinator"] as Role[]) {
  const visible = new Set(visibleModules(role));
  for (const name of ["Administration", "Security", "Platform Operations", "AI Governance"]) {
    check(`${role}: cannot see ${name}`, !visible.has(name));
  }
}
check("Student cannot see Student Information or Analytics", !visibleModules("Student").some((n) => n === "Student Information" || n === "Analytics"));
check("Only the Administrator role sees Administration", roles.every((r) => visibleModules(r).includes("Administration") === (r === "Administrator")));

// Backend roles that the UI folds into "Administrator" get a narrower list.
check("institution_admin is unrestricted", allowListForBackendRoles(["institution_admin"]) === null);
check("platform_super_admin is unrestricted", allowListForBackendRoles(["platform_super_admin", "finance_admin"]) === null);
const finance = visibleModules("Administrator", ["finance_admin"]);
check("finance_admin sees billing but not teaching or security modules", finance.includes("Administration") && finance.includes("Reports") && !finance.includes("Courses") && !finance.includes("Security") && !finance.includes("Platform Operations"), finance.join(", "));
check("finance_admin gets a short list", finance.length === 6, `got ${finance.length}`);
const support = visibleModules("Administrator", ["support_officer"]);
check("support_officer sees proctoring (Assessments) and compliance modules", ["Assessments", "Security", "AI Governance", "Data Security & Privacy"].every((m) => support.includes(m)), support.join(", "));
check("support_officer cannot see Administration or Courses", !support.includes("Administration") && !support.includes("Courses"));
check("unrestricted roles are unchanged by backend roles", visibleModules("Teacher / Faculty", ["teacher"]).length === 25);

console.log(`\n${failures} failure(s)`);
process.exit(failures ? 1 : 0);
