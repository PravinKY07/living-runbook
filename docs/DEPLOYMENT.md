# Deployment Guide

This guide deploys the FastAPI backend to a Python-compatible host and the React/Vite frontend to Vercel.

Never commit `.env`, session secrets, database files, or deployment credentials.

## 1. Deploy the backend first

Create a Python web service in Render or another Python-compatible host.

Recommended settings:

```text
Repository: PravinKY07/living-runbook
Root directory: backend
Build command: pip install . && python -m app.cli.seed_demo_users
Start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
Health check: /api/health
```

Set the backend environment variables in the hosting dashboard:

```text
APP_ENV=production
DATABASE_PATH=./data/living_runbook.db
SESSION_SECRET=<long random private value>
SESSION_HTTPS_ONLY=true
SESSION_SAME_SITE=none
CORS_ORIGINS=["https://your-frontend.vercel.app"]
DEMO_EDITOR_PASSWORD=<private Editor demo password>
DEMO_APPROVER_PASSWORD=<private Approver demo password>
```

### Where the SQLite database lives

`DATABASE_PATH` is **relative to the backend root directory**, so
`./data/living_runbook.db` resolves to `backend/data/living_runbook.db` inside the
deployed service. The application creates the directory if it is missing.

Do **not** use `/var/data` unless you have attached a paid persistent disk. On
Render's Free tier no disk is attached, the build runs as a non-root user, and
`/var/data` cannot be created, so the service fails to start. If you do attach a
persistent disk, mount it and point `DATABASE_PATH` at a path inside that mount.

Without a persistent disk the SQLite file is **ephemeral**: it survives sleep and
spin-down, but a redeploy erases it. See the rollback warning in section 4.

`DEMO_EDITOR_PASSWORD` and `DEMO_APPROVER_PASSWORD` are required by the build
command, which seeds the two demo users on every deploy. Never commit them or
paste them into chat or source control.

Before deploying the backend, create the Vercel project without deploying it so you know its exact `*.vercel.app` URL. Put that URL in `CORS_ORIGINS`. Deploy the frontend only after the backend health check passes.

Do not put these values in Git or in frontend environment variables.

After deployment, verify:

```text
https://your-backend.example.com/api/health
```

Expected response:

```json
{"status":"ok"}
```

The demo users are seeded by the build command, so no separate seeding step is
needed after a successful deploy. `python -m app.cli.seed_demo_users` reads
`DEMO_EDITOR_PASSWORD` and `DEMO_APPROVER_PASSWORD` from the environment; it only
falls back to an interactive prompt when it is run from a terminal.

Because redeploying re-runs the build, redeploys are safe for login: the demo users
are always recreated. Runbook versions and audit events are not preserved across a
redeploy unless a persistent disk is attached.

## 2. Deploy the frontend second

Create a Vercel project from the same repository.

Recommended settings:

```text
Root directory: frontend
Build command: npm run build
Output directory: dist
```

Set this Vercel environment variable after the backend URL is known:

```text
VITE_API_BASE_URL=https://your-backend.example.com
```

The frontend must not receive `SESSION_SECRET`, `DATABASE_PATH`, or `CORS_ORIGINS`.

For the manually triggered living-runbook workflow, configure the repository variable:

```text
RUNBOOK_API_URL=https://your-backend.example.com
```

Configure these as protected GitHub Actions secrets:

```text
RUNBOOK_DEMO_EMAIL
RUNBOOK_DEMO_PASSWORD
```

The workflow only proposes a pull request. It does not publish directly.

Deploy the frontend and verify the login flow in a clean browser session.

## 3. Live verification

Use the seeded accounts:

```text
editor@example.test
approver@example.test
```

Verify:

1. Editor login.
2. Submission of `https://github.com/PravinKY07/runbook-demo-fixture`.
3. Completed static analysis.
4. Evidence-backed Markdown runbook.
5. Safe Q&A and refusal behavior.
6. Approver approval.
7. Publishing.
8. Approver-only audit endpoint.

## 4. Rollback

If a deployment fails, redeploy the last known-good Git commit. Do not delete the database or change secrets as a first troubleshooting step.

> **Warning: on a host without a persistent disk, a redeploy erases the SQLite
> database.** Runbooks, runbook versions, approvals, and audit events are lost. The
> demo users are recreated automatically by the build command, but the analyzed
> runbooks are not. After any redeploy, re-run the analysis in section 3 to rebuild
> the runbook before demonstrating it. Attach a paid persistent disk to avoid this.

## 5. Security notes

- The backend is not deployed to Vercel serverless functions.
- Only the static React frontend is deployed to Vercel.
- The backend stores its SQLite database at the relative path
  `DATABASE_PATH` (for example `backend/data/living_runbook.db`).
- **MVP limitation:** on a host without a persistent disk, such as Render's Free
  tier, that database is ephemeral and a redeploy erases it. Persistent storage
  requires a paid disk, and a later migration to PostgreSQL is planned.
- Public GitHub repository input is validated before cloning.
- Repository code is never executed.
- The GitHub Action must propose pull requests and never publish directly.
