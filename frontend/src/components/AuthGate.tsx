"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Dashboard } from "@/components/Dashboard";
import { FullPageStatus } from "@/components/FullPageStatus";
import { getSession, login, logout, register } from "@/lib/api";

type Credentials = {
  username: string;
  password: string;
};

const initialCredentials: Credentials = { username: "", password: "" };

export const AuthGate = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [credentials, setCredentials] = useState(initialCredentials);
  const [error, setError] = useState("");

  useEffect(() => {
    getSession()
      .then((data) => setIsAuthenticated(data.authenticated))
      .catch(() => setIsAuthenticated(false));
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");

    try {
      if (mode === "register") {
        await register(credentials.username, credentials.password);
      } else {
        await login(credentials.username, credentials.password);
      }
      setIsAuthenticated(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Something went wrong.");
    }
  };

  const handleLogout = async () => {
    await logout().catch(() => undefined);
    setCredentials(initialCredentials);
    setIsAuthenticated(false);
  };

  const handleUnauthorized = useCallback(() => setIsAuthenticated(false), []);

  if (isAuthenticated === null) {
    return <FullPageStatus loadingText="Loading..." />;
  }

  if (isAuthenticated) {
    return <Dashboard onLogout={handleLogout} onUnauthorized={handleUnauthorized} />;
  }

  const isRegister = mode === "register";

  return (
    <main className="grid min-h-screen place-items-center bg-[var(--surface)] p-6">
      <form
        aria-label={isRegister ? "Create account" : "Sign in"}
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-3xl border border-[var(--stroke)] bg-white p-8 shadow-[var(--shadow)]"
      >
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[var(--primary-blue)]">
          Project Management
        </p>
        <h1 className="mt-3 font-display text-3xl font-semibold text-[var(--navy-dark)]">
          {isRegister ? "Create your account" : "Welcome back"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-[var(--gray-text)]">
          {isRegister
            ? "Register to get your own boards and AI copilot."
            : "Sign in to open your boards."}
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
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
        <button
          type="submit"
          className="mt-6 w-full rounded-full bg-[var(--secondary-purple)] px-4 py-3 text-sm font-semibold text-white"
        >
          {isRegister ? "Create account" : "Sign in"}
        </button>
        <button
          type="button"
          onClick={() => {
            setError("");
            setMode(isRegister ? "login" : "register");
          }}
          className="mt-4 w-full text-center text-sm font-semibold text-[var(--primary-blue)]"
        >
          {isRegister ? "Already have an account? Sign in" : "New here? Create an account"}
        </button>
      </form>
    </main>
  );
};
