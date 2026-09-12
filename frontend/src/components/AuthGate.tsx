"use client";

import { FormEvent, useEffect, useState } from "react";
import { KanbanBoard } from "@/components/KanbanBoard";

type Credentials = {
  username: string;
  password: string;
};

const initialCredentials: Credentials = { username: "", password: "" };

export const AuthGate = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [credentials, setCredentials] = useState(initialCredentials);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/auth/session")
      .then((response) => response.json())
      .then((data: { authenticated: boolean }) => setIsAuthenticated(data.authenticated))
      .catch(() => setIsAuthenticated(false));
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");

    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
    });

    if (!response.ok) {
      setError("Use user and password to sign in.");
      return;
    }

    setIsAuthenticated(true);
  };

  const handleLogout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    setCredentials(initialCredentials);
    setIsAuthenticated(false);
  };

  if (isAuthenticated === null) {
    return <main className="grid min-h-screen place-items-center">Loading…</main>;
  }

  if (isAuthenticated) {
    return <KanbanBoard onLogout={handleLogout} onUnauthorized={() => setIsAuthenticated(false)} />;
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[var(--surface)] p-6">
      <form
        aria-label="Sign in"
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-3xl border border-[var(--stroke)] bg-white p-8 shadow-[var(--shadow)]"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[var(--primary-blue)]">
          Project Management MVP
        </p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-[var(--navy-dark)]">
          Welcome back
        </h1>
        <p className="mt-3 text-sm leading-6 text-[var(--gray-text)]">
          Sign in to open your Kanban board.
        </p>
        <label className="mt-8 block text-sm font-semibold text-[var(--navy-dark)]">
          Username
          <input
            aria-label="Username"
            value={credentials.username}
            onChange={(event) =>
              setCredentials((current) => ({ ...current, username: event.target.value }))
            }
            className="mt-2 w-full rounded-xl border border-[var(--stroke)] px-3 py-2 outline-none focus:border-[var(--primary-blue)]"
            required
          />
        </label>
        <label className="mt-4 block text-sm font-semibold text-[var(--navy-dark)]">
          Password
          <input
            aria-label="Password"
            type="password"
            value={credentials.password}
            onChange={(event) =>
              setCredentials((current) => ({ ...current, password: event.target.value }))
            }
            className="mt-2 w-full rounded-xl border border-[var(--stroke)] px-3 py-2 outline-none focus:border-[var(--primary-blue)]"
            required
          />
        </label>
        {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
        <button
          type="submit"
          className="mt-6 w-full rounded-full bg-[var(--secondary-purple)] px-4 py-3 text-sm font-semibold text-white"
        >
          Sign in
        </button>
      </form>
    </main>
  );
};
