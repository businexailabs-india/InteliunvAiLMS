# BusineX AI Edu Lab — Current State

## Executive summary

The repository is a frontend-only product prototype running in Figma Make. The current interface is branded **IntelUniVen AI Edu Lab**, while the requested target product name is **BusineX AI Edu Lab**. Product naming, visual assets, legal text, and migration of existing brand references require an explicit rebranding decision; discovery does not silently rewrite the working application.

The prototype demonstrates a broad enterprise LMS information architecture and many high-fidelity workflows, but it does not yet contain production application services.

The prototype must be preserved as the visual and interaction reference while production foundations are introduced incrementally. Existing UI states and sample data must not be described as persisted, secure, realtime, or AI-backed functionality.

## Repository inventory

| Area | Current implementation | Evidence |
|---|---|---|
| Frontend | React 19 single-page application | `src/main.tsx`, `src/App.tsx` |
| Build | Vite 8, TypeScript strict mode | `vite.config.ts`, `tsconfig.json` |
| Styling | Tailwind CSS v4 import plus custom CSS | `src/index.css`, `src/intelligence.css`, `src/ai-deep-dive.css` |
| Routing | Component state (`module`, `sub`, `detail`) | `src/App.tsx` |
| State | Local React state only | `src/App.tsx` |
| Backend | Not present | No server application or API routes |
| Database | Not present | No schema, ORM, migrations, or database dependencies |
| Authentication | Simulated role switcher | No identity provider, sessions, JWT validation, or password/OTP flow |
| Authorization | UI visibility rules only | `roleHidden` in `src/App.tsx` |
| Multi-tenancy | Demonstration screens only | No tenant-scoped persistence or database enforcement |
| AI | Static sample outputs and interactive mock states | No provider SDK, gateway, RAG, metering, or model calls |
| Object storage | Not present | No storage adapter or upload pipeline |
| Vector retrieval | Not present | No embeddings, vector store, or retrieval service |
| Background jobs | Not present | No queue, scheduler, or worker |
| Realtime | UI simulation only | No application WebSocket service |
| Billing | Demonstration navigation/data only | No ledger, pricing table, invoices, or payment integration |
| Tests | Not present | No unit, integration, E2E, or accessibility test setup |
| CI/CD | Not present | No workflow definitions |
| Infrastructure | Figma Make preview/deploy helpers only | `.figma/make/`; no containers or IaC |
| Observability | Not present | No structured logging, tracing, metrics, or alerting |
| Environment config | No application `.env` files found | Repository scan |
| Product name | Current UI: IntelUniVen; requested target: BusineX | `src/App.tsx`, product brief |

No secrets were found or printed during discovery.

## Implemented prototype experiences

The following are implemented as frontend demonstrations with local state and sample data:

- Role experiences for Student, Teacher/Faculty, Parent/Guardian, and Administrator
- Dashboard, course catalog, course details, lessons, and course builder
- Learning Intelligence and 28 learning model workspaces
- AI Study Buddy, adaptive learning, and student success deep dives
- Syllabus-grounded assessment authoring and teacher review
- Assignment, submission, grading, rubric, similarity, and feedback workspaces
- Assessment proctoring and integrity-review prototype
- Gamification, Digital Quotient, and live quiz arena prototype
- Multi-tenant security and privacy command-center prototype
- Analytics, student information, administration, governance, and operations mock screens
- Human-in-the-loop labels, sample-data labels, confidence indicators, and advisory AI language
- Interactive local-state workspaces for learning paths, communication, collaboration, academic management, virtual classrooms, digital library, integrations, credentials, and live quiz hosting

## Partially implemented areas

These areas have strong UI coverage but no production service layer:

| Capability | Present | Missing |
|---|---|---|
| Roles | UI role switcher and menu visibility | Authenticated identities, scoped assignments, permission checks |
| Multi-tenancy | Tenant selection and security visualization | Tenant context, API enforcement, PostgreSQL RLS, storage isolation |
| Courses | Catalog, detail, builder screens | CRUD APIs, persistence, versioning, enrollment rules |
| Question generation | Syllabus and review UI | Document extraction, model gateway, JSON validation, provenance |
| Study Buddy | Conversation and citation UI | RAG, tenant-isolated retrieval, safety, rate limits, retention |
| Assignments | Detailed workflows | Uploads, malware scanning, deadlines, durable approvals |
| Assessments | Builder and question review | Question bank, deterministic grading, scheduling, attempts |
| Proctoring | Policy and evidence UI | Consent records, camera integration, secure browser, event service |
| Analytics | Dashboards and predictions UI | Event model, warehouse, verified metrics, model monitoring |
| Results | Navigation concepts | Calculation engine, report cards, corrections, audit trail |
| Gamification | Multi-level interactive prototype | Event ledger, rules engine, durable awards, realtime sessions |
| Security/privacy | Control-plane prototype | Enforced policies, key management, audit sink, rights workflows |

## Code characteristics and constraints

- `src/App.tsx` is a large monolithic file (approximately 1,200 lines at discovery) containing navigation, mock data, primitives, and feature screens.
- CSS is similarly concentrated in three files and uses established visual tokens in `src/index.css`.
- There is no browser router. Deep links, refresh-safe URLs, and route authorization are absent.
- Many controls are intentionally demonstrative; several do not persist or call a service.
- Static sample values are clearly labeled in many critical workflows and should remain labeled until replaced by trusted data.
- The Vite development server is supervised by Figma Make and must not be started manually.

## Current security posture

The repository cannot currently provide production security guarantees because there is no trusted server boundary.

- Client-side role hiding is not authorization.
- Client-side tenant selection is not tenant isolation.
- No authenticated actor or institution context is cryptographically established.
- No server-side validation, audit logging, encryption-key integration, upload scanning, or rate limiting exists.
- No data is persisted by the app, which limits current exposure but also means workflows are prototypes.

## Build baseline

The prescribed verification command is:

```bash
pnpm build
```

The application builds successfully. Vite reports a non-blocking warning because the monolithic JavaScript bundle is larger than 500 kB after minification. Route-level code splitting should be introduced during frontend modularization.

## Conclusion

The current repository is a valuable UX specification, not a production LMS implementation. The production path should preserve the React/Vite experience and add a versioned API, PostgreSQL tenant model, identity integration, worker services, object storage, AI gateway, testing, and operations controls behind it. Rebranding to BusineX should be handled as a deliberate, testable migration rather than mixed ad hoc with the P0 security foundation.
