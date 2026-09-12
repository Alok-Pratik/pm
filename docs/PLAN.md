# Project Management MVP plan

This is the implementation checklist for the local, single-user MVP. Each part
ends with a review and approval checkpoint; work on the next part does not start
until the preceding part is approved.

## Shared decisions

- The frontend is a Next.js static export. FastAPI serves its built files at `/`;
  Next.js server-side rendering and API routes are not used.
- FastAPI is the sole backend API server and Docker runs the complete application.
- SQLite is the persistent database. JSON is used for API payloads and where useful
  in SQLite; a separate JSON-file database is not used.
- The MVP login accepts only `user` / `password`, while records retain a user
  relationship for future multi-user support.
- A signed-in user has one board with five fixed, renameable columns.
- OpenRouter uses `nvidia/nemotron-3-ultra-550b-a55b:free`; its key stays on the
  backend and out of client assets and source control.

## Part 1: Planning and frontend documentation

- [x] Review requirements and the existing frontend.
- [x] Record implementation steps, checks, and success criteria here.
- [x] Add `frontend/AGENTS.md` describing current code and tests.
- [x] Request approval before scaffolding.

Tests and success criteria:

- The plan covers required features, deployment constraints, validation, and
  approval gates.
- Frontend guidance accurately reflects the checked-in code.
- User approval is received before Part 2 starts.

## Part 2: Docker, FastAPI, and local scripts

- [x] Create the Python backend in `backend/`, using `uv` inside Docker.
- [x] Add a minimal FastAPI app with health and example JSON API endpoints.
- [x] Configure Docker to install the Python app with `uv` and start FastAPI.
- [x] Serve temporary example static HTML at `/` during scaffolding.
- [x] Add Docker Compose start/stop scripts for macOS/Linux and Windows PowerShell.
- [x] Document only the commands needed to run and test the app.
- [x] Verify the Docker workflow in a Docker-capable environment.
- [x] Request approval before integrating the real frontend.

Tests and success criteria:

- Clean `docker compose up --build` works without a host Python or Node runtime.
- `GET /health` succeeds; the example page at `/` can call the example API.
- Each platform script starts and stops the same Compose application.

## Part 3: Static frontend integration

- [x] Configure a Next.js static export compatible with FastAPI static serving.
- [x] Replace the temporary page with the existing Kanban UI at `/`.
- [x] Preserve five columns, renaming, card creation/removal, and drag-and-drop.
- [x] Verify static assets resolve from FastAPI in Docker.
- [x] Add Docker-targeted browser-test configuration alongside unit tests.
- [x] Run browser integration tests after the Playwright browser download completes.
- [x] Request approval before authentication.

Tests and success criteria:

- The Docker-served page renders the existing Kanban and assets.
- Unit tests cover board operations and core UI interactions.
- Browser tests cover load, rename, create, delete, and movement.
- A production Docker build serves the app.

## Part 4: MVP sign-in and sign-out

- [x] Add backend credential validation, a signed HTTP-only session cookie, and
  login/logout/current-session endpoints.
- [x] Show login first; accept only `user` / `password` and report invalid input.
- [x] Protect board APIs when they are added in Part 6; show login again when a
  session is absent.
- [x] Add sign-out that clears the session.
- [x] Verify authentication API and browser flows in Docker.
- [x] Request approval before database design.

Tests and success criteria:

- Valid credentials grant access; invalid credentials and anonymous API board
  requests do not.
- Logout invalidates both UI and API access.
- Backend tests cover session cases and browser tests cover login/logout.

## Part 5: Database-model proposal and approval

- [x] Write a concise schema proposal in `docs/` before implementation.
- [x] Model users, one board per user, fixed columns, cards, membership, and order.
- [x] Specify SQLite constraints, indexes, first-run creation, and API JSON-to-table
  mapping.
- [x] Include an example board response and atomic move/multi-card update approach.
- [x] Request explicit schema approval before Part 6.

Tests and success criteria:

- The proposed design represents all board interactions and future per-user
  ownership without a JSON-file datastore.
- It enforces one board per user and preserves card order.
- No schema implementation begins before approval.

## Part 6: Persistent backend API

- [x] Create the SQLite file and schema automatically when absent.
- [x] Deterministically seed/create the MVP user's board on first use.
- [x] Implement authenticated read, column rename, card create/edit/delete, move,
  and ordering endpoints.
- [x] Validate inputs and use transactions to preserve board consistency.
- [x] Return a canonical complete board after mutations.
- [x] Add isolated-database backend unit/integration tests.
- [x] Request approval before production UI integration.

Tests and success criteria:

- A missing database becomes one usable board for the MVP user.
- Mutations persist across restart.
- Invalid input, IDs, and auth failures neither corrupt the board nor succeed.
- Tests prove ordering, cross-column moves, and ownership.

## Part 7: Persistent frontend/backend Kanban

- [x] Load the signed-in user's board from the API rather than demo-only state.
- [x] Send all rename, create, edit, delete, move, and order operations to FastAPI.
- [x] Add simple loading and recoverable error states.
- [x] Update UI state from each canonical API response.
- [x] Expand unit and browser tests to use the real API contract in Docker.
- [x] Request approval before AI connectivity.

Tests and success criteria:

- Board changes survive reload and container restart.
- UI handles both successful and failed requests correctly.
- Browser tests prove all signed-in board interactions against FastAPI and SQLite.

## Part 8: OpenRouter connectivity

- [x] Add backend-only configuration reading `OPENROUTER_API_KEY`.
- [x] Implement a small OpenRouter service using the selected model.
- [x] Run a non-public development connectivity check using `2+2`.
- [x] Give clear missing-key/upstream-failure configuration errors.
- [x] Mock upstream HTTP in automated tests; use the real key only for the manual
  connectivity check.
- [x] Request approval before AI board mutations.

Tests and success criteria:

- With a configured key, the service receives a valid response to `2+2`.
- Tests cover request construction and error cases without external calls.
- Keys never reach browser bundles, logs, tests, or committed files.

## Part 9: AI board-aware structured response

- [x] Define a versioned structured response: assistant message plus optional,
  validated board operations.
- [x] Send current board JSON, user message, and bounded conversation history.
- [x] Validate structured model output server-side before database changes.
- [x] Apply valid multi-card operations atomically; reject invalid operations with
  no partial update.
- [x] Associate MVP conversation history with the user and board.
- [x] Test no-op chat, one/multiple operations, malformed output, and invalid IDs.
- [x] Request approval before chat UI.

Tests and success criteria:

- AI can reply without a board change or make validated changes atomically.
- Invalid/unsupported model output leaves the board untouched.
- Arbitrary model text is never executed as a database operation.

## Part 10: AI chat sidebar

- [x] Add a responsive, accessible sidebar matching the specified colors.
- [x] Provide history, input, sending state, and readable error feedback.
- [x] Send authenticated chat requests and render assistant responses.
- [x] Refresh board state from the canonical response after AI mutations.
- [x] Test desktop and narrow viewport usability.
- [x] Run the full automated suite and request final acceptance.

Tests and success criteria:

- Users can chat and see AI-driven board changes without manual refresh.
- The sidebar is keyboard usable with labelled controls.
- Unit, backend integration, and browser suites pass in Docker.
- The documented command starts the entire MVP locally.
