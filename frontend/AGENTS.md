# Frontend guide

## Current application

This folder contains the Kanban Studio UI: Next.js 16, React 19, TypeScript,
and Tailwind CSS 4. Authentication and board persistence use the FastAPI API
served from the same origin.

`src/app/page.tsx` renders `KanbanBoard`; `src/app/layout.tsx` supplies metadata;
`src/app/globals.css` defines the project color and font tokens.

## Board implementation

- `KanbanBoard.tsx` loads canonical `BoardData` from FastAPI and owns the view state and `@dnd-kit/core` drag/drop events.
- `KanbanColumn` is droppable and renames its title immediately.
- `KanbanCard` is sortable, editable, and removable; `NewCardForm` creates cards; the preview
  component is used by the drag overlay.
- `src/lib/kanban.ts` defines the data types, sample data, ordering/move helper,
  and temporary client ID generator. `src/lib/api.ts` contains board and chat
  requests, including persisted history hydration. Card order lives in
  `Column.cardIds`.

FastAPI is the source of truth; update the local view from canonical API
responses. The finished frontend must be statically exported
and served by FastAPI. Do not add Next.js API routes or server-side rendering.

## Commands

Run from this directory:

```bash
npm install
npm run dev
npm run lint
npm run test:unit
npm run test:e2e
npm run build
```

Unit tests use Vitest and Testing Library. Component tests are beside source where
practical; setup is in `src/test/`. Playwright browser tests are in `tests/`.
Update tests whenever UI behavior changes.

## Constraints

- Keep five fixed columns; their names, not their count, may change.
- Maintain labelled controls, keyboard access, and visible focus behavior.
- Use yellow `#ecad0a`, blue `#209dd7`, purple `#753991`, navy `#032147`, and
  gray `#888888` project tokens.
- Never expose backend or OpenRouter secrets in frontend code, built environment,
  logs, or test snapshots.
