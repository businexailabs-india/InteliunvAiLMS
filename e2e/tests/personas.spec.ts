import { expect, test } from "@playwright/test";
import { visibleModules, type Role } from "../../src/access.ts";
import { expectLiveScreen, login, openModule, probe, sidebarModules } from "./helpers";

interface Screen {
  module: string;
  sub?: string;
  heading: string;
}

interface Persona {
  email: string;
  uiRole: Role;
  backendRoles: string[];
  modules: number;
  screens: Screen[];
}

const PERSONAS: Persona[] = [
  {
    email: "aarav.sharma@inteluniven.edu",
    uiRole: "Student",
    backendRoles: ["student"],
    modules: 18,
    screens: [
      { module: "Assignments", heading: "Assignments" },
      { module: "Attendance", heading: "Attendance" },
      { module: "Gradebook", heading: "Results" },
    ],
  },
  {
    email: "maya.chen@inteluniven.edu",
    uiRole: "Teacher / Faculty",
    backendRoles: ["teacher"],
    modules: 25,
    screens: [
      { module: "Assignments", heading: "Assignment Management" },
      { module: "Attendance", heading: "Attendance Management" },
      { module: "Gradebook", heading: "Gradebook" },
      { module: "Assessments", sub: "Question Bank", heading: "Question Bank & Quiz Builder" },
      { module: "Assessments", sub: "Proctoring", heading: "Integrity Review" },
    ],
  },
  {
    email: "riya.nair@inteluniven.edu",
    uiRole: "Training Coordinator",
    backendRoles: ["coordinator"],
    modules: 10,
    screens: [
      { module: "Attendance", heading: "Attendance Management" },
      { module: "Student Information", heading: "Student & Batch Management" },
      { module: "Assignments", heading: "Assignment Management" },
      { module: "Assessments", sub: "Results", heading: "Assessment Score Management" },
      { module: "Assessments", sub: "Proctoring", heading: "Integrity Review" },
    ],
  },
  {
    email: "priya.sharma@inteluniven.edu",
    uiRole: "Parent / Guardian / HOD",
    backendRoles: ["parent_guardian"],
    modules: 19,
    screens: [
      { module: "Attendance", heading: "Attendance" },
      { module: "Gradebook", heading: "Results" },
    ],
  },
  {
    email: "david.wilson@inteluniven.edu",
    uiRole: "Principal / L&D Lead",
    backendRoles: ["principal_academic_director"],
    modules: 23,
    screens: [{ module: "Analytics", heading: "Cohort Completion Report" }],
  },
  {
    email: "olivia.harris@inteluniven.edu",
    uiRole: "Administrator",
    backendRoles: ["institution_admin"],
    modules: 30,
    screens: [
      { module: "Administration", sub: "Billing", heading: "Subscription & AI Usage" },
      { module: "Analytics", heading: "Cohort Completion Report" },
      { module: "Assessments", sub: "Proctoring", heading: "Integrity Review" },
    ],
  },
];

for (const persona of PERSONAS) {
  test.describe(persona.uiRole, () => {
    test(`sidebar matches the access rules (${persona.modules} modules)`, async ({ page }) => {
      const seen = probe(page);
      await login(page, persona.email);
      const actual = await sidebarModules(page);
      expect(actual).toHaveLength(persona.modules);
      expect(actual.sort()).toEqual(visibleModules(persona.uiRole, persona.backendRoles).sort());
      expect(seen.errors).toEqual([]);
    });

    for (const screen of persona.screens) {
      const label = `${screen.module}${screen.sub ? ` > ${screen.sub}` : ""} shows "${screen.heading}" with no API errors`;
      test(label, async ({ page }) => {
        const seen = probe(page);
        await login(page, persona.email);
        await sidebarModules(page);
        await openModule(page, screen.module, screen.sub);
        await expectLiveScreen(page, screen.heading);
        expect(seen.errors, "uncaught page errors").toEqual([]);
        expect(seen.apiFailures, "API calls that failed").toEqual([]);
      });
    }
  });
}
