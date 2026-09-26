# Living Runbook Generator — Reviewer Context

Last updated: 2026-09-25

## Project overview

Living Runbook Generator is a secure, evidence-backed documentation system for public GitHub repositories. It analyzes a repository's service structure, dependencies, configuration, and failure-handling paths, then produces a Markdown runbook for engineers.

The product is intentionally not a generic chatbot or a simple repository summarizer. Important findings must include valid source-file and line-number evidence.

## MVP scope

The planned MVP includes:

- Public GitHub repository URL submission
- Read-only repository loading
- GitHub URL validation and SSRF protection
- Safe file allowlist and resource limits
- Secret and PII redaction before model calls
- No execution of analyzed repository code
- Service Mapper analysis
- Failure Analyzer analysis
- Dependency Mapper analysis
- Configuration Analyzer analysis
- Structured JSON analysis results
- Evidence-validated Markdown runbooks
- Final runbook secret scanning
- Minimal React/Vite frontend
- Safe Q&A limited to sanitized project data
- Runbook versions and diffs
- Manually triggered GitHub Action that proposes pull-request updates
- Seeded demo authentication with Editor and Approver roles
- Human approval before publishing an official runbook
- Audit logging

## Technology

- **Backend:** Python 3.11+, FastAPI, Pydantic
- **Frontend:** React with Vite
- **Database:** SQLite for the MVP
- **Backend hosting:** Render or another Python-compatible host with persistent storage
- **Frontend hosting:** Vercel
- **Analysis providers:** StaticProvider for AST/regex analysis and MockProvider for tests and fallback demos, both behind one model gateway
- **External model provider:** None required for the MVP
- **Development environment:** IBM Bob IDE

All analysis providers use the same gateway. Output must be labeled as `static` or `mock`. The application does not claim that local output came from an external model.

## Security model

- Accept only validated public GitHub HTTPS repository URLs initially.
- Reject local, private, link-local, internal, malformed, and unsupported destinations.
- Treat repository content as untrusted data.
- Never execute repository source, scripts, tests, migrations, Docker files, or package hooks.
- Use temporary workspaces and delete them after success or failure.
- Allowlist files and enforce repository, file, path, and time limits.
- Ignore or reject secrets, credentials, private keys, databases, archives, and binaries.
- Redact secrets and PII before provider calls and scan the final Markdown again.
- Validate structured model output with schemas.
- Verify that cited files exist and line numbers are valid.
- Never execute generated commands.
- Use Argon2 password hashing and HTTP-only sessions.
- Enforce Editor and Approver roles in the backend.
- Require human approval before publishing.
- Keep audit logs free of raw secrets and unnecessary source code.

## Intended architecture

```text
React/Vite frontend
        |
FastAPI backend
  - authentication and roles
  - URL validation and read-only repository loading
  - temporary workspace and file policy
  - redaction and resource limits
  - model gateway
      - Service Mapper
      - Failure Analyzer
      - Dependency Mapper
      - Configuration Analyzer
  - structured-output and evidence validation
  - Runbook Writer
  - final secret scan
  - draft/version storage
  - human approval
  - audit logging
```

The four analysis components operate on the sanitized repository manifest. Raw repository content is temporary; sanitized analysis, runbooks, metadata, approvals, and audit events are retained.

## Reviewer demo flow

The intended demonstration is:

1. Sign in with a seeded demo user.
2. Submit the safe public demo repository.
3. Watch analysis progress.
4. Review the four structured analysis sections.
5. Open source references and verify file/line evidence.
6. Review the generated Markdown runbook.
7. Ask a question using only the sanitized runbook and approved analysis.
8. Compare runbook versions if available.
9. Sign in as an Approver and approve the draft.
10. Confirm the audit history and proposed GitHub Action update.

## GitHub Action behavior

The action begins with `workflow_dispatch`. It analyzes changes through the hosted backend, creates a versioned runbook diff, and proposes a pull request for human review. It does not execute repository code or publish directly.

## Current implementation status

The MVP backend and frontend are implemented locally. The current checkout includes the FastAPI backend, static analyzers, runbook generation and approval services, audit endpoint, React/Vite frontend, deployment documentation, and a manually triggered GitHub Action. See the README and deployment guide for current runnable commands and verification steps.

No credentials, API keys, passwords, private repository data, or `.env` values belong in this document or the public repository.

## Repository documentation

- [`README.md`](./README.md) — public overview and setup
- [`AGENTS.md`](./AGENTS.md) — project source of truth, architecture, security requirements, and implementation rules
- [`.env.example`](./.env.example) — safe configuration template
- `bob_sessions/` — required IBM Bob task-session evidence screenshots:
  - `phase-0-bob-session-evidence.png` — Phase 0 foundation and health endpoint session
  - `phase-5-bob-security-review.png` — read-only security review of the analysis and approval flow
  - `phase-5-audit-endpoint-bob-task.png` — audit endpoint review task
  - `final-live-demo.png` — live deployed demo, added after the Render and Vercel deployment
  - `final-bob-task-summary.png` — final deployment-readiness verification, added after deployment

## Scope boundaries

The MVP does not include Slack, PagerDuty, automatic production remediation, service restarts, arbitrary command execution, full malware scanning, SSO/SAML/SCIM, multi-tenant support, predictive incident prevention, automatic postmortems, broad web browsing, Jev AI, or automatic publishing without human approval.

## MVP success criteria

The MVP is successful when a public repository can be analyzed safely, an evidence-backed draft runbook can be generated and inspected, Q&A remains limited to sanitized project data, changes can be versioned, and an official runbook cannot be published without human approval.
