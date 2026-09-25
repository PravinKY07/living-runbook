# Deployment Guide

This guide deploys the FastAPI backend to a Python-compatible host and the React/Vite frontend to Vercel.

Never commit `.env`, session secrets, database files, or deployment credentials.

## 1. Deploy the backend first

Create a Python web service in Render or another Python-compatible host.

Recommended settings:

```text
Repository: PravinKY07/living-runbook
Root directory: backend
Build command: pip install .
Start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
Health check: /api/health
```

The backend must have a persistent disk. Mount it at:

```text
/var/data
```

Set the backend environment variables in the hosting dashboard:

```text
APP_ENV=production
DATABASE_PATH=/var/data/living_runbook.db
SESSION_SECRET=<long random private value>
SESSION_HTTPS_ONLY=true
SESSION_SAME_SITE=none
CORS_ORIGINS=["https://your-frontend.vercel.app"]
```

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

Then open the Render shell and seed the demo users:

```text
python -m app.cli.seed_demo_users
```

The command prompts for private Editor and Approver passwords. Do not paste those passwords into chat or source control.

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

## 5. Security notes

- The backend is not deployed to Vercel serverless functions.
- Only the static React frontend is deployed to Vercel.
- The backend must use persistent SQLite storage.
- Public GitHub repository input is validated before cloning.
- Repository code is never executed.
- The GitHub Action must propose pull requests and never publish directly.
