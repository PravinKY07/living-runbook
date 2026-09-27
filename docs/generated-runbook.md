# Service Runbook

> Generated from sanitized static analysis. Human approval is required before publishing.

## Provenance

- Provider: `static`
- Repository: `https://github.com/PravinKY07/runbook-demo-fixture`
- Commit: `105c1c2a200752f3e42c0e389ad27288ab1c0f9e`
- Files analyzed: `7`
- Repository code was not executed.

## Service overview

- Name: Fixture Orders API
- Purpose: A small FastAPI orders service used to demonstrate static repository analysis. — evidence: `app.py:1`
- Language: Python
- Framework: fastapi

## Entry points

- **route**: Route handler: health. — `app.py:22`
- **route**: Route handler: list_orders. — `app.py:40`

## External calls

- **external_call**: External call candidate: requests.get. — `app.py:31`

## Dependencies

- `python:3.12-slim` — build; evidence: `Dockerfile:1`
- `fastapi` >=0.100.0 — runtime; evidence: `requirements.txt:1`
- `uvicorn` >=0.20.0 — runtime; evidence: `requirements.txt:2`
- `requests` >=2.31.0 — runtime; evidence: `requirements.txt:3`

## Configuration

- `database` (database) — evidence: `.env.example:1`; value withheld
- `DATABASE_URL` (constant) — evidence: `.env.example:1`; value withheld
- `timeout` (timeout) — evidence: `.env.example:2`; value withheld
- `REQUEST_TIMEOUT` (constant) — evidence: `.env.example:2`; value withheld
- `INVENTORY_URL` (constant) — evidence: `.env.example:3`; value withheld
- `feature_flag` (flag) — evidence: `README.md:9`; value withheld
- `timeout` (timeout) — evidence: `README.md:12`; value withheld
- `INVENTORY_URL` (environment) — evidence: `app.py:17`; value withheld
- `MAX_ATTEMPTS` (constant) — evidence: `app.py:18`; value withheld
- `timeout` (timeout) — evidence: `app.py:26`; value withheld
- `timeout` (timeout) — evidence: `app.py:31`; value withheld
- `database` (database) — evidence: `app.py:43`; value withheld
- `timeout` (timeout) — evidence: `app.py:44`; value withheld
- `DATABASE_URL` (environment) — evidence: `config.py:6`; value withheld
- `database` (database) — evidence: `config.py:6`; value withheld
- `REQUEST_TIMEOUT` (environment) — evidence: `config.py:7`; value withheld
- `timeout` (timeout) — evidence: `config.py:7`; value withheld
- `database` (database) — evidence: `database.py:5`; value withheld
- `database` (database) — evidence: `database.py:6`; value withheld

## Failure modes

- **raise**: Explicit exception-raising path detected. — `app.py:36`
- **try_except**: Exception-handling path detected. — `app.py:42`
- **try_except**: Exception-handling path detected. — `app.py:30`
- **exception_handler**: Exception handler detected. — `app.py:46`
- **exception_handler**: Exception handler detected. — `app.py:34`
- **timeout_or_retry**: Failure signal detected: timeout or retry. — `app.py:26`
- **timeout_or_retry**: Failure signal detected: timeout or retry. — `app.py:31`
- **raise**: Explicit exception-raising path detected. — `database.py:7`

## Diagnostic guidance

- Confirm the cited file and line before acting on a finding.
- Check the referenced configuration names without exposing their values.
- Review database and external-service error handling before maintenance.
- Generated commands are not executed by this application.

## Evidence

- `app.py:22` — def health():
- `app.py:40` — def list_orders():
- `app.py:31` — response = requests.get(INVENTORY_URL, timeout=timeout)
- `app.py:36` — raise RuntimeError("Inventory service is unavailable.") from last_error
- `app.py:42` — try:
- `app.py:30` — try:
- `app.py:46` — except DatabaseUnavailable:
- `app.py:34` — except requests.RequestException as exc:
- `app.py:26` — def fetch_inventory(timeout: int) -> dict:
- `database.py:7` — raise DatabaseUnavailable("Database configuration is missing.")
- `.env.example:1` — DATABASE_URL=sqlite:///./fixture.db
- `.env.example:2` — REQUEST_TIMEOUT=5
- `.env.example:3` — INVENTORY_URL=https://inventory.example/v1
- `README.md:9` — - Environment-based configuration
- `README.md:12` — - A timeout setting that is actually applied to the outbound request
- `app.py:17` — INVENTORY_URL = os.getenv("INVENTORY_URL", "https://inventory.example/v1")
- `app.py:18` — MAX_ATTEMPTS = 2
- `app.py:43` — connection = get_connection(settings.database_url)
- `app.py:44` — inventory = fetch_inventory(settings.request_timeout)
- `config.py:6` — self.database_url = os.getenv("DATABASE_URL", "sqlite:///./fixture.db")
- `config.py:7` — self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "5"))
- `database.py:5` — def get_connection(database_url: str):
- `database.py:6` — if not database_url:
- `Dockerfile:1` — FROM python:3.12-slim
- `requirements.txt:1` — fastapi>=0.100.0
- `requirements.txt:2` — uvicorn>=0.20.0
- `requirements.txt:3` — requests>=2.31.0

## Limitations

- Static analysis cannot prove runtime behavior or deployment state.
- Unknown facts remain unknown rather than being invented.
- This draft requires an Approver before publication.

