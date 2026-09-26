import { useEffect, useState } from "react";

import { api, API_BASE } from "./api.js";

const POLL_INTERVAL_MS = 1000;

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function buildLineDiff(previousContent, currentContent) {
  const previousLines = previousContent.split("\n");
  const currentLines = currentContent.split("\n");
  const diff = [];
  const lineCount = Math.max(previousLines.length, currentLines.length);

  for (let index = 0; index < lineCount; index += 1) {
    const previousLine = previousLines[index] ?? "";
    const currentLine = currentLines[index] ?? "";
    if (previousLine === currentLine) {
      diff.push(`  ${currentLine}`);
    } else {
      if (previousLine) diff.push(`- ${previousLine}`);
      if (currentLine) diff.push(`+ ${currentLine}`);
    }
  }

  return diff.join("\n");
}

async function waitForJob(jobId, onUpdate) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const job = await api.getJob(jobId);
    onUpdate(job);
    if (job.status === "completed" || job.status === "failed") {
      return job;
    }
    await wait(POLL_INTERVAL_MS);
  }
  throw new Error("Analysis is taking longer than expected. Try again shortly.");
}

function LoginForm({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      onLogin(await api.login(email, password));
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell centered">
      <section className="card auth-card">
        <p className="eyebrow">Secure analysis workspace</p>
        <h1>Living Runbook Generator</h1>
        <p className="muted">
          Safe, evidence-backed operational runbooks from a public GitHub repository.
        </p>
        <p className="callout">
          <strong>Read before testing.</strong> This is a demo instance for evaluation,
          not a production service. It produces an <strong>unverified draft</strong>{" "}
          runbook from static analysis, so findings may be wrong or incomplete. It never
          executes repository code, never deploys or changes anything, and cannot read
          private repositories. Verify every finding against the source before acting on
          it. Full caveats and suggested tests are in the <code>README</code>.
        </p>
        <form onSubmit={handleSubmit} className="stack">
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="fine-print">
          Demo only. Repository content is treated as untrusted data and is never executed.
        </p>
      </section>
    </main>
  );
}

function Header({ user, onLogout }) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Living Runbook Generator</p>
        <h1>Evidence-backed operations</h1>
      </div>
      <div className="user-actions">
        <span className="role-badge">{user.role}</span>
        <span className="muted">{user.email}</span>
        {user.role === "approver" && (
          <a
            className="audit-link"
            href={`${API_BASE}/api/audit`}
            target="_blank"
            rel="noreferrer"
          >
            Audit log (JSON)
          </a>
        )}
        <button type="button" className="secondary" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </header>
  );
}

function RepositoryForm({ onJob, onError, busy }) {
  const [repositoryUrl, setRepositoryUrl] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    onError("");
    try {
      const job = await api.submitRepository(repositoryUrl);
      onJob(job);
      const finishedJob = await waitForJob(job.id, onJob);
      if (finishedJob.status === "failed") {
        throw new Error(finishedJob.error_message || "Repository analysis failed safely.");
      }
    } catch (submitError) {
      onError(submitError.message);
    }
  }

  return (
    <section className="card">
      <p className="eyebrow">Step 1</p>
      <h2>Analyze a public repository</h2>
      <p className="muted">
        Only public <code>github.com</code> repository URLs are accepted. The backend clones
        read-only, redacts sensitive values, and never runs repository code.
      </p>
      <form onSubmit={handleSubmit} className="stack">
        <label>
          Public GitHub repository URL
          <input
            type="url"
            value={repositoryUrl}
            onChange={(event) => setRepositoryUrl(event.target.value)}
            placeholder="https://github.com/owner/project"
            required
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Analyzing repository…" : "Start safe analysis"}
        </button>
      </form>
    </section>
  );
}

function JobStatus({ job }) {
  if (!job) {
    return null;
  }
  return (
    <section className="card status-card">
      <p className="eyebrow">Step 2</p>
      <h2>Analysis status</h2>
      <div className="status-row">
        <span className={`status status-${job.status}`}>{job.status}</span>
        <span className="muted">Job {job.id}</span>
      </div>
      {job.runbook_id && <p className="success">Draft runbook created.</p>}
      {job.error_message && <p className="error">{job.error_message}</p>}
    </section>
  );
}

function RunbookView({ runbook, runbookId, user, onRunbook, onError }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState("");

  useEffect(() => {
    if (!runbookId || !runbook) {
      return undefined;
    }
    api
      .getRunbookVersions(runbookId)
      .then((storedVersions) => {
        setVersions(storedVersions);
        setSelectedVersion(String(runbook.metadata.version));
      })
      .catch((versionsError) => onError(versionsError.message));
    return undefined;
  }, [runbookId, runbook?.metadata.version]);

  async function handleAsk(event) {
    event.preventDefault();
    setBusy(true);
    onError("");
    try {
      setAnswer(await api.ask(runbookId, question));
    } catch (askError) {
      onError(askError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleApproval(action) {
    setBusy(true);
    onError("");
    try {
      onRunbook(await action(runbookId));
    } catch (approvalError) {
      onError(approvalError.message);
    } finally {
      setBusy(false);
    }
  }

  if (!runbook) {
    return null;
  }

  const metadata = runbook.metadata;
  const canApprove = user.role === "approver";
  const selectedDraft = versions.find(
    (version) => String(version.metadata.version) === selectedVersion,
  );
  const diffContent =
    selectedDraft && selectedDraft.metadata.version !== metadata.version
      ? buildLineDiff(selectedDraft.content, runbook.content)
      : "";

  return (
    <>
      <section className="card runbook-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Step 3</p>
            <h2>Generated runbook</h2>
          </div>
          <span className="provider-badge">Provider: {metadata.provider}</span>
        </div>
        <div className="runbook-meta">
          <span>Version {metadata.version}</span>
          <span>Status: {metadata.status}</span>
          {metadata.repository_commit && <span>Commit: {metadata.repository_commit.slice(0, 12)}</span>}
        </div>
        <p className="callout">
          <strong>Draft output from static analysis.</strong> Findings are unverified and
          may be wrong or incomplete. Check them against the source before acting on them.
        </p>
        <pre className="runbook-content">{runbook.content}</pre>
        <div className="approval-actions">
          {canApprove ? (
            <>
              <button
                type="button"
                disabled={busy || metadata.status !== "draft"}
                onClick={() => handleApproval(api.approve)}
              >
                Approve draft
              </button>
              <button
                type="button"
                className="secondary"
                disabled={busy || metadata.status !== "approved"}
                onClick={() => handleApproval(api.publish)}
              >
                Publish approved runbook
              </button>
            </>
          ) : (
            <p className="muted">An Approver must review and publish this runbook.</p>
          )}
        </div>
      </section>

      <section className="card">
        <p className="eyebrow">Version history</p>
        <h2>Compare runbook versions</h2>
        {versions.length <= 1 ? (
          <p className="muted">Only the current version is available.</p>
        ) : (
          <>
            <label>
              Version
              <select
                value={selectedVersion}
                onChange={(event) => setSelectedVersion(event.target.value)}
              >
                {versions.map((version) => (
                  <option key={version.metadata.version} value={version.metadata.version}>
                    Version {version.metadata.version} ({version.metadata.status})
                  </option>
                ))}
              </select>
            </label>
            {diffContent && (
              <>
                <p className="muted">Changes from the selected version to the current version:</p>
                <pre className="version-diff">{diffContent}</pre>
              </>
            )}
          </>
        )}
      </section>

      <section className="card">
        <p className="eyebrow">Safe Q&amp;A</p>
        <h2>Ask about this runbook</h2>
        <p className="muted">
          Answers are retrieved only from the stored runbook. No external browsing or command
          execution is available.
        </p>
        <form onSubmit={handleAsk} className="ask-form">
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What failure paths are documented?"
            required
          />
          <button type="submit" disabled={busy || !question.trim()}>
            Ask
          </button>
        </form>
        {answer && (
          <div className="answer">
            <p className="answer-text">{answer.answer}</p>
            {answer.citations.length > 0 && (
              <p className="muted">Citations: {answer.citations.join(", ")}</p>
            )}
          </div>
        )}
      </section>
    </>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [job, setJob] = useState(null);
  const [runbook, setRunbook] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoadingSession(false));
  }, []);

  async function handleLogout() {
    await api.logout().catch(() => undefined);
    setUser(null);
    setJob(null);
    setRunbook(null);
  }

  async function handleJobUpdate(nextJob) {
    setJob(nextJob);
    if (nextJob.status === "completed" && nextJob.runbook_id) {
      try {
        setRunbook(await api.getRunbook(nextJob.runbook_id));
      } catch (runbookError) {
        setError(runbookError.message);
      }
    }
  }

  if (loadingSession) {
    return (
      <main className="shell centered">
        <p className="muted">Loading session…</p>
      </main>
    );
  }

  if (!user) {
    return <LoginForm onLogin={setUser} />;
  }

  return (
    <main className="shell">
      <Header user={user} onLogout={handleLogout} />
      {error && <p className="error banner">{error}</p>}
      <RepositoryForm
        busy={busy}
        onError={setError}
        onJob={(nextJob) => {
          setBusy(true);
          handleJobUpdate(nextJob).finally(() => setBusy(false));
        }}
      />
      <JobStatus job={job} />
      <RunbookView
        runbook={runbook}
        runbookId={job?.runbook_id}
        user={user}
        onRunbook={(nextRunbook) => {
          setRunbook(nextRunbook);
          setJob((currentJob) =>
            currentJob
              ? { ...currentJob, status: nextRunbook.metadata.status }
              : currentJob,
          );
        }}
        onError={setError}
      />
    </main>
  );
}
