"use client";

import { FormEvent, useState } from "react";
import type { BoardSummary } from "@/lib/kanban";

type BoardSwitcherProps = {
  boards: BoardSummary[];
  error?: string;
  onOpen: (boardId: string) => void;
  onCreate: (title: string) => Promise<void>;
  onRename: (boardId: string, title: string) => Promise<void>;
  onDelete: (boardId: string) => Promise<void>;
  onLogout?: () => void;
};

export const BoardSwitcher = ({ boards, error, onOpen, onCreate, onRename, onDelete, onLogout }: BoardSwitcherProps) => {
  const [newTitle, setNewTitle] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!newTitle.trim() || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onCreate(newTitle.trim());
      setNewTitle("");
    } finally {
      setIsSubmitting(false);
    }
  };

  const startRename = (board: BoardSummary) => {
    setRenamingId(board.id);
    setRenameValue(board.title);
  };

  const submitRename = async (boardId: string) => {
    const title = renameValue.trim();
    setRenamingId(null);
    if (title) await onRename(boardId, title);
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-16">
      <div className="flex items-start justify-between gap-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[var(--primary-blue)]">
            Project Management
          </p>
          <h1 className="mt-3 font-display text-3xl font-semibold text-[var(--navy-dark)]">
            Your boards
          </h1>
        </div>
        {onLogout && (
          <button
            type="button"
            onClick={onLogout}
            className="rounded-full border border-[var(--stroke)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--navy-dark)]"
          >
            Sign out
          </button>
        )}
      </div>

      {error && (
        <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {boards.length === 0 ? (
        <p className="text-sm leading-6 text-[var(--gray-text)]">
          You don&apos;t have any boards yet. Create your first one below.
        </p>
      ) : (
        <ul className="flex flex-col gap-3" aria-label="Boards">
          {boards.map((board) => (
            <li
              key={board.id}
              className="flex items-center justify-between gap-4 rounded-2xl border border-[var(--stroke)] bg-white px-5 py-4 shadow-[var(--shadow)]"
            >
              {renamingId === board.id ? (
                <input
                  aria-label={`Rename ${board.title}`}
                  autoFocus
                  value={renameValue}
                  onChange={(event) => setRenameValue(event.target.value)}
                  onBlur={() => submitRename(board.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      (event.target as HTMLInputElement).blur();
                    }
                    if (event.key === "Escape") setRenamingId(null);
                  }}
                  className="flex-1 rounded-xl border border-[var(--stroke)] px-3 py-2 text-sm outline-none focus:border-[var(--primary-blue)]"
                />
              ) : (
                <button
                  type="button"
                  onClick={() => onOpen(board.id)}
                  className="flex-1 text-left font-semibold text-[var(--navy-dark)]"
                >
                  {board.title}
                </button>
              )}
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => startRename(board)}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.15em] text-[var(--navy-dark)]"
                >
                  Rename
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(board.id)}
                  className="rounded-full border border-[var(--stroke)] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.15em] text-red-700"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleCreate} className="flex items-end gap-3 rounded-2xl border border-[var(--stroke)] bg-white p-5 shadow-[var(--shadow)]">
        <label className="flex-1 text-sm font-semibold text-[var(--navy-dark)]">
          New board
          <input
            aria-label="New board title"
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="e.g. Marketing launch"
            className="mt-2 w-full rounded-xl border border-[var(--stroke)] px-3 py-2 text-sm outline-none focus:border-[var(--primary-blue)]"
          />
        </label>
        <button
          type="submit"
          disabled={isSubmitting || !newTitle.trim()}
          className="rounded-full bg-[var(--secondary-purple)] px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Create board
        </button>
      </form>
    </main>
  );
};
