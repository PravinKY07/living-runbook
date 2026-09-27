// Credentials for the two seeded demo accounts on the public evaluation
// instance. The quick sign-in buttons below submit these to the ordinary
// POST /api/auth/login endpoint, so the backend still verifies the password
// against the stored Argon2 hash and still resolves the role server-side. The
// browser never asserts a role -- these values are credentials only.
//
// These accounts are throwaway. The instance holds no real data, its database
// is ephemeral, and the same values are published in this repository's pinned
// issue, so compiling them into the public bundle adds no confidentiality
// loss. See the "Demo accounts" section of README.md.
export const DEMO_ACCOUNTS = {
  editor: {
    label: "Editor",
    email: "editor@example.test",
    password: "liviNgB00k_81%!",
  },
  approver: {
    label: "Approver",
    email: "approver@example.test",
    password: "app91_/,ranbuk",
  },
};
