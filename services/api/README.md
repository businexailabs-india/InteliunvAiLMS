# BusineX API foundation

This is the first P0 vertical-slice scaffold. It is not a complete LMS backend.

## Included

- FastAPI service and `/health`
- Provider-neutral OIDC JWT validation
- Keycloak development realm configuration
- PostgreSQL models for institutions, users, memberships, roles, role assignments, and audit logs
- Separate migration-owner and runtime database roles
- Forced RLS on tenant-owned foundation tables
- `GET /api/v1/institutions/current`
- Authorized `PATCH /api/v1/institutions/current` with audit logging
- Cloud-neutral Docker Compose topology for PostgreSQL, Redis, Keycloak, and API
- Frontend institution-service mock and HTTP adapters

## Local stack

From the repository root:

```bash
docker compose -f infra/containers/compose.yaml build api
docker compose -f infra/containers/compose.yaml up
```

Endpoints:

- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`
- Keycloak: `http://localhost:8080`

The values in `config.example.env` and the Compose role passwords are local-development
defaults, not production secrets. Production deployments must inject credentials from a
secret manager and rotate them independently.

## Verification

Frontend:

```bash
pnpm build
```

Backend, after installing the development extra in a Python environment:

```bash
python -m pip install -e 'services/api[dev]'
pytest services/api/tests
ruff check services/api
```

Database isolation checks require a migrated PostgreSQL instance and must run as
`businex_app`, not the table owner:

```bash
psql "$BUSINEX_APP_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f services/api/tests/test_tenant_isolation.sql
```

## Not yet complete

- Production identity-provider claim mapping and login callback
- Seed/bootstrap command for development institutions and memberships
- Frontend screen integration with the HTTP adapter
- Permission catalog and full seven-role authorization matrix
- End-to-end PostgreSQL/API cross-tenant tests
- CI pipeline, secret scanning, container scanning, and deployment manifests
- Account recovery and transactional email/SMS provider
- BusineX application rebrand
