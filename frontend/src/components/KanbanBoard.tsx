"use client";

import { useEffect, useState } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
  closestCorners,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { KanbanColumn } from "@/components/KanbanColumn";
import { KanbanCardPreview } from "@/components/KanbanCardPreview";
import { ChatSidebar } from "@/components/ChatSidebar";
import { FullPageStatus } from "@/components/FullPageStatus";
import type { BoardData } from "@/lib/kanban";
import { describeApiError, notifyIfUnauthorized } from "@/lib/api";
import * as api from "@/lib/api";

type KanbanBoardProps = {
  boardId: string;
  onBack?: () => void;
  onLogout?: () => void;
  onUnauthorized?: () => void;
};

export const KanbanBoard = ({ boardId, onBack, onLogout, onUnauthorized }: KanbanBoardProps) => {
  const [board, setBoard] = useState<BoardData | null>(null);
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const cardsById = board?.cards ?? {};

  useEffect(() => {
    api.getBoard(boardId).then(setBoard).catch((reason) => {
      notifyIfUnauthorized(reason, onUnauthorized);
      setError(describeApiError(reason, "The board request failed."));
    });
  }, [boardId, onUnauthorized]);

  const apply = async (operation: Promise<BoardData>): Promise<boolean> => {
    setError("");
    try {
      setBoard(await operation);
      return true;
    } catch (reason) {
      notifyIfUnauthorized(reason, onUnauthorized);
      setError(describeApiError(reason, "The board request failed."));
      return false;
    }
  };

  const handleDragCancel = () => {
    setActiveCardId(null);
  };

  const handleDragStart = (event: DragStartEvent) => {
    setActiveCardId(event.active.id as string);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveCardId(null);

    if (!board || !over || active.id === over.id) {
      return;
    }
    const targetColumn = board.columns.find((column) => column.id === over.id || column.cardIds.includes(over.id as string));
    if (!targetColumn) return;
    const position = targetColumn.id === over.id ? targetColumn.cardIds.length : targetColumn.cardIds.indexOf(over.id as string);
    void apply(api.moveCard(boardId, active.id as string, targetColumn.id, position));
  };

  const handleRenameColumn = (columnId: string, title: string) => {
    if (title.trim()) return apply(api.renameColumn(boardId, columnId, title));
    return Promise.resolve(false);
  };

  const handleAddCard = (columnId: string, title: string, details: string) => {
    void apply(api.createCard(boardId, columnId, title, details));
  };

  const handleDeleteCard = (columnId: string, cardId: string) => {
    void apply(api.deleteCard(boardId, cardId));
  };

  const handleEditCard = (cardId: string, title: string, details: string) => {
    void apply(api.updateCard(boardId, cardId, title, details));
  };

  if (!board) {
    return <FullPageStatus loadingText="Loading board..." error={error} />;
  }

  const activeCard = activeCardId ? cardsById[activeCardId] : null;

  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute left-0 top-0 h-[420px] w-[420px] -translate-x-1/3 -translate-y-1/3 rounded-full bg-[radial-gradient(circle,_rgba(32,157,215,0.25)_0%,_rgba(32,157,215,0.05)_55%,_transparent_70%)]" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-[520px] w-[520px] translate-x-1/4 translate-y-1/4 rounded-full bg-[radial-gradient(circle,_rgba(117,57,145,0.18)_0%,_rgba(117,57,145,0.05)_55%,_transparent_75%)]" />

      <main className="relative mx-auto flex min-h-screen max-w-[1760px] flex-col gap-10 px-6 pb-16 pt-12">
        <header className="flex flex-col gap-6 rounded-[32px] border border-[var(--stroke)] bg-white/80 p-8 shadow-[var(--shadow)] backdrop-blur">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-[var(--gray-text)]">
                Kanban Studio
              </p>
              <h1 className="mt-3 font-display text-4xl font-semibold text-[var(--navy-dark)]">
                {board.title}
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-[var(--gray-text)]">
                Keep momentum visible. Rename columns, drag cards between stages,
                and capture quick notes without getting buried in settings.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              {onBack && (
                <button
                  type="button"
                  onClick={onBack}
                  className="rounded-full border border-[var(--stroke)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--navy-dark)]"
                >
                  All boards
                </button>
              )}
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
          </div>
          <div className="flex flex-wrap items-center gap-4">
            {board.columns.map((column) => (
              <div
                key={column.id}
                className="flex items-center gap-2 rounded-full border border-[var(--stroke)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--navy-dark)]"
              >
                <span className="h-2 w-2 rounded-full bg-[var(--accent-yellow)]" />
                {column.title}
              </div>
            ))}
          </div>
        </header>
        {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}

        <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
          <DndContext
            sensors={sensors}
            collisionDetection={closestCorners}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            <div className="min-w-0 overflow-x-auto pb-2">
              <section className="board-lane gap-6">
                {board.columns.map((column) => (
                  <KanbanColumn
                    key={column.id}
                    column={column}
                    cards={column.cardIds.map((cardId) => board.cards[cardId])}
                    onRename={handleRenameColumn}
                    onAddCard={handleAddCard}
                    onDeleteCard={handleDeleteCard}
                    onEditCard={handleEditCard}
                  />
                ))}
              </section>
            </div>
            <DragOverlay>
              {activeCard ? (
                <div className="w-[260px]">
                  <KanbanCardPreview card={activeCard} />
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
          <ChatSidebar boardId={boardId} onBoardUpdate={setBoard} onUnauthorized={onUnauthorized} />
        </div>
      </main>
    </div>
  );
};
