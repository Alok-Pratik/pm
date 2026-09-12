# Backend guide

This folder contains the FastAPI application served by the Docker container.
`app/main.py` owns the application instance and routes. Keep the backend as the
sole API server; the frontend will later be statically exported and served here.

Run backend tests from this directory with:

```bash
uv sync --all-groups
uv run pytest
```

Use small route modules and plain, typed Python. Add backend tests in `tests/`
for every endpoint or persistence behavior. Keep credentials and OpenRouter keys
in environment configuration only; never return or log them.
