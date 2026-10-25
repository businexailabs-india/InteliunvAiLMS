# IntelUniVen AI Edu Lab — Backend Implementation Starter

This supplement is intended to accompany the uploaded application. The existing repository already includes a FastAPI identity/tenant foundation, PostgreSQL migrations, Keycloak, Redis and Docker Compose. Do not overwrite these files blindly.

## Deliverables
- `seed_synthetic.py`: reproducible fictional tenant/user/course/enrollment/assessment/attendance/gamification/AI/proctoring/invoice JSON datasets.
- `api-contract.yaml`: illustrative OpenAPI contract for the next LMS vertical slices (not yet implemented).
- `IMPLEMENTATION.md`: implementation priorities and safety/tenant requirements.

## Generate data
`python seed_synthetic.py --output ./synthetic-data --students 2000`

All records are fabricated. Seed output is JSON for ingestion after the real schema and authorization model have been finalized. No seed records are inserted into PostgreSQL automatically.
