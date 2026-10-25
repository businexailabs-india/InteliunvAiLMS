/**
 * Which sidebar modules each user may see.
 *
 * This only shapes navigation. The API enforces permissions independently, so hiding a module is
 * never the security boundary. Kept free of React so it can be tested with plain Node.
 */

export type Role =
  | "Student"
  | "Teacher / Faculty"
  | "Training Coordinator"
  | "Parent / Guardian / HOD"
  | "Principal / L&D Lead"
  | "Administrator";

export const ALL_MODULES = [
  "Dashboard",
  "Courses",
  "Learning Paths",
  "Assignments",
  "Assessments",
  "Virtual Classroom",
  "Digital Library",
  "Learning Intelligence",
  "AI & Personalization",
  "AI Study Buddy",
  "Adaptive Learning",
  "Teaching Copilot",
  "Student Success",
  "Collaboration",
  "Gamification",
  "Calendar",
  "Communication",
  "Student Information",
  "Attendance",
  "Gradebook",
  "Credentials",
  "Analytics",
  "Reports",
  "Data & AI Platform",
  "Integrations",
  "Administration",
  "Data Security & Privacy",
  "Security",
  "AI Governance",
  "Platform Operations",
] as const;

export const roleHidden: Record<Role, string[]> = {
  Student: ["Teaching Copilot", "Student Information", "Student Success", "Analytics", "Reports", "Data & AI Platform", "Integrations", "Administration", "Data Security & Privacy", "Security", "AI Governance", "Platform Operations"],
  "Teacher / Faculty": ["Data & AI Platform", "Administration", "Data Security & Privacy", "Security", "Platform Operations"],
  // Coordinators review assignment submissions, so Assignments is visible to them.
  "Training Coordinator": ["Courses", "Learning Paths", "Virtual Classroom", "Digital Library", "Learning Intelligence", "AI & Personalization", "AI Study Buddy", "Adaptive Learning", "Teaching Copilot", "Student Success", "Collaboration", "Gradebook", "Credentials", "Data & AI Platform", "Integrations", "Administration", "Data Security & Privacy", "Security", "AI Governance", "Platform Operations"],
  // Parents see their linked learner's published results, so Gradebook is visible to them.
  "Parent / Guardian / HOD": ["Learning Paths", "Virtual Classroom", "Teaching Copilot", "Collaboration", "Data & AI Platform", "Integrations", "Administration", "Data Security & Privacy", "Security", "AI Governance", "Platform Operations"],
  "Principal / L&D Lead": ["AI Study Buddy", "Teaching Copilot", "Data & AI Platform", "Administration", "Data Security & Privacy", "Security", "Platform Operations"],
  Administrator: [],
};

/**
 * Backend roles that the UI folds into "Administrator" but that should not see everything.
 * Returns null when the user has no extra restriction.
 */
export function allowListForBackendRoles(roles: string[]): string[] | null {
  const codes = new Set(roles);
  if (codes.has("institution_admin") || codes.has("platform_super_admin")) return null;
  if (codes.has("finance_admin")) {
    return ["Dashboard", "Analytics", "Reports", "Administration", "Calendar", "Communication"];
  }
  if (codes.has("support_officer")) {
    return [
      "Dashboard",
      "Assessments",
      "Student Information",
      "Attendance",
      "Student Success",
      "Calendar",
      "Communication",
      "Reports",
      "Data Security & Privacy",
      "Security",
      "AI Governance",
    ];
  }
  return null;
}

/** Modules visible for a UI role, further narrowed by the signed-in user's backend roles. */
export function visibleModules(role: Role, backendRoles: string[] = []): string[] {
  const hidden = new Set(roleHidden[role]);
  const allow = allowListForBackendRoles(backendRoles);
  return ALL_MODULES.filter((name) => !hidden.has(name) && (allow === null || allow.includes(name)));
}
