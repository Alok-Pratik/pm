# Project Management MVP

## Run

Create a root `.env` file containing `OPENROUTER_API_KEY` before starting the
application. The key is passed only to the backend container.

macOS/Linux:

```bash
./scripts/start.sh
```

Windows PowerShell:

```powershell
./scripts/start.ps1
```

Open `http://localhost:8000`. Stop the application with the matching `stop`
script.

## Test the Docker-served frontend

```bash
cd frontend
npm install
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8000 npm run test:e2e
```

## Test backend

```bash
cd backend
uv sync --all-groups
uv run pytest
```
