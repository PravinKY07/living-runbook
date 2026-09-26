# Service Runbook

> Generated from sanitized static analysis. Human approval is required before publishing.

## Provenance

- Provider: `static`
- Repository: `https://github.com/PravinKY07/runbook-demo-fixture`
- Commit: `bc8e9fb90de7bb65a3cdcd9c930a405319c6990c`
- Files analyzed: `7`
- Repository code was not executed.

## Service overview

- Name: Fixture Orders API
- Purpose: Not established by static analysis
- Language: Python
- Framework: fastapi

## Entry points

- **route**: Route handler: health. — `app.py:10`
- **route**: Route handler: list_orders. — `app.py:15`

## External calls

- No external call candidates were detected.

## Dependencies

- `python:3.12-slim` — build; evidence: `Dockerfile:1`
- `fastapi` >=0.100.0 — runtime; evidence: `requirements.txt:1`
- `uvicorn` >=0.20.0 — runtime; evidence: `requirements.txt:2`

## Configuration

- `DATABASE_URL` (environment) — evidence: `.env.example:1`; value withheld
- `database` (database) — evidence: `.env.example:1`; value withheld
- `REQUEST_TIMEOUT` (environment) — evidence: `.env.example:2`; value withheld
- `timeout` (timeout) — evidence: `.env.example:2`; value withheld
- `feature_flag` (flag) — evidence: `README.md:9`; value withheld
- `timeout` (timeout) — evidence: `README.md:12`; value withheld
- `database` (database) — evidence: `app.py:18`; value withheld
- `DATABASE_URL` (environment) — evidence: `config.py:6`; value withheld
- `database` (database) — evidence: `config.py:6`; value withheld
- `REQUEST_TIMEOUT` (environment) — evidence: `config.py:7`; value withheld
- `timeout` (timeout) — evidence: `config.py:7`; value withheld
- `database` (database) — evidence: `database.py:5`; value withheld
- `database` (database) — evidence: `database.py:6`; value withheld

## Failure modes

- **try_except**: Exception-handling path detected. — `app.py:17`
- **exception_handler**: Exception handler detected. — `app.py:20`
- **raise**: Explicit exception-raising path detected. — `database.py:7`

## Diagnostic guidance

- Confirm the cited file and line before acting on a finding.
- Check the referenced configuration names without exposing their values.
- Review database and external-service error handling before maintenance.
- Generated commands are not executed by this application.

## Evidence

- `app.py:10` — def health():
- `app.py:15` — def list_orders():
- `app.py:17` — try:
- `app.py:20` — except DatabaseUnavailable:
- `database.py:7` — raise DatabaseUnavailable("Database configuration is missing.")
- `.env.example:1` — DATABASE_URL=sqlite:///./fixture.db
- `.env.example:1` — DATABASE_URL=sqlite:///./fixture.db
- `.env.example:2` — REQUEST_TIMEOUT=5
- `.env.example:2` — REQUEST_TIMEOUT=5
- `README.md:9` — - Environment-based configuration
- `README.md:12` — - A timeout setting
- `app.py:18` — connection = get_connection(settings.database_url)
- `config.py:6` — self.database_url = os.getenv("DATABASE_URL", "sqlite:///./fixture.db")
- `config.py:6` — self.database_url = os.getenv("DATABASE_URL", "sqlite:///./fixture.db")
- `config.py:7` — self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "5"))
- `config.py:7` — self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "5"))
- `database.py:5` — def get_connection(database_url: str):
- `database.py:6` — if not database_url:

## Limitations

- Static analysis cannot prove runtime behavior or deployment state.
- Unknown facts remain unknown rather than being invented.
- This draft requires an Approver before publication.

