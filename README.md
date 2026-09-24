# Living Runbook Generator

A secure, evidence-backed runbook generator that analyzes a public GitHub repository and produces operational documentation from the current code, dependencies, configuration, and failure-handling paths.

## Project document

Before building, read [`AGENTS.md`](./AGENTS.md). It is the source of truth for the product scope, security requirements, architecture, testing strategy, and implementation order.

## MVP goal

A user should be able to:

1. Open the web application.
2. Submit a public GitHub repository URL.
3. See safe analysis progress.
4. Generate a Markdown runbook with source evidence.
5. Ask questions about the service.
6. Review runbook versions and diffs.
7. Approve a runbook before publishing it.

## Security promise

The analyzer treats repository content as untrusted input. It does not execute repository code, does not expose secrets, validates model output, and requires human approval for official runbook changes.
