const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the generic safe message when the response is not JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export const api = {
  login: (email, password) =>
    request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request("/api/auth/me"),
  submitRepository: (repositoryUrl) =>
    request("/api/repositories/analyze", {
      method: "POST",
      body: JSON.stringify({ repository_url: repositoryUrl }),
    }),
  getJob: (jobId) => request(`/api/jobs/${jobId}`),
  getRunbook: (runbookId) => request(`/api/runbooks/${runbookId}`),
  ask: (runbookId, question) =>
    request(`/api/runbooks/${runbookId}/ask`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  approve: (runbookId) =>
    request(`/api/runbooks/${runbookId}/approve`, { method: "POST" }),
  publish: (runbookId) =>
    request(`/api/runbooks/${runbookId}/publish`, { method: "POST" }),
};
