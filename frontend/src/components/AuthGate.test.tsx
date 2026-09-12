import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthGate } from "@/components/AuthGate";

vi.mock("@/components/Dashboard", () => ({
  Dashboard: ({ onLogout }: { onLogout?: () => void }) => (
    <div>
      <h1>Dashboard</h1>
      {onLogout && <button type="button" onClick={onLogout}>Sign out</button>}
    </div>
  ),
}));

type FetchResponse = { ok: boolean; json: object };

const stubFetch = (map: Record<string, FetchResponse>) => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const entry = Object.entries(map).find(([key]) => url.includes(key));
      if (!entry) return Promise.reject(new Error(`Unmocked fetch: ${url}`));
      const res = entry[1];
      return Promise.resolve({ ok: res.ok, json: () => Promise.resolve(res.json) });
    })
  );
};

afterEach(() => vi.unstubAllGlobals());

describe("AuthGate", () => {
  it("shows login form when session is not authenticated", async () => {
    stubFetch({ "/api/auth/session": { ok: true, json: { authenticated: false } } });
    render(<AuthGate />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument()
    );
  });

  it("shows the dashboard directly when already authenticated", async () => {
    stubFetch({ "/api/auth/session": { ok: true, json: { authenticated: true, username: "user" } } });
    render(<AuthGate />);
    await waitFor(() =>
      expect(screen.getByText("Dashboard")).toBeInTheDocument()
    );
  });

  it("transitions to the dashboard on successful login", async () => {
    stubFetch({
      "/api/auth/session": { ok: true, json: { authenticated: false } },
      "/api/auth/login": { ok: true, json: { authenticated: true, username: "user" } },
    });
    render(<AuthGate />);
    await waitFor(() => screen.getByRole("button", { name: /sign in/i }));

    await userEvent.type(screen.getByLabelText("Username"), "user");
    await userEvent.type(screen.getByLabelText("Password"), "password");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText("Dashboard")).toBeInTheDocument()
    );
  });

  it("shows an error on invalid credentials", async () => {
    stubFetch({
      "/api/auth/session": { ok: true, json: { authenticated: false } },
      "/api/auth/login": { ok: false, json: { detail: "Invalid credentials" } },
    });
    render(<AuthGate />);
    await waitFor(() => screen.getByRole("button", { name: /sign in/i }));

    await userEvent.type(screen.getByLabelText("Username"), "user");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument()
    );
  });

  it("returns to login after logout", async () => {
    stubFetch({
      "/api/auth/session": { ok: true, json: { authenticated: true, username: "user" } },
      "/api/auth/logout": { ok: true, json: { authenticated: false } },
    });
    render(<AuthGate />);
    await waitFor(() => screen.getByText("Dashboard"));

    await userEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument()
    );
  });

  it("switches to the register form and creates an account", async () => {
    stubFetch({
      "/api/auth/session": { ok: true, json: { authenticated: false } },
      "/api/auth/register": { ok: true, json: { authenticated: true, username: "newperson" } },
    });
    render(<AuthGate />);
    await waitFor(() => screen.getByRole("button", { name: /sign in/i }));

    await userEvent.click(screen.getByRole("button", { name: /new here\? create an account/i }));
    await waitFor(() => screen.getByRole("button", { name: /^create account$/i }));

    await userEvent.type(screen.getByLabelText("Username"), "newperson");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: /^create account$/i }));

    await waitFor(() =>
      expect(screen.getByText("Dashboard")).toBeInTheDocument()
    );
  });

  it("shows an error when registration fails", async () => {
    stubFetch({
      "/api/auth/session": { ok: true, json: { authenticated: false } },
      "/api/auth/register": { ok: false, json: { detail: "Username is already taken" } },
    });
    render(<AuthGate />);
    await waitFor(() => screen.getByRole("button", { name: /sign in/i }));

    await userEvent.click(screen.getByRole("button", { name: /new here\? create an account/i }));
    await userEvent.type(screen.getByLabelText("Username"), "taken");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: /^create account$/i }));

    await waitFor(() =>
      expect(screen.getByText(/username is already taken/i)).toBeInTheDocument()
    );
  });
});
