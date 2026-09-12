import { useState, type FormEvent } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import clsx from "clsx";
import type { Card } from "@/lib/kanban";

type KanbanCardProps = {
  card: Card;
  onDelete: (cardId: string) => void;
  onEdit: (cardId: string, title: string, details: string) => void;
};

export const KanbanCard = ({ card, onDelete, onEdit }: KanbanCardProps) => {
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(card.title);
  const [details, setDetails] = useState(card.details);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: card.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const openEdit = () => {
    setTitle(card.title);
    setDetails(card.details);
    setIsEditing(true);
  };

  const cancelEdit = () => {
    setTitle(card.title);
    setDetails(card.details);
    setIsEditing(false);
  };

  return (
    <article
      ref={setNodeRef}
      style={style}
      className={clsx(
        "rounded-2xl border border-transparent bg-white px-4 py-4 shadow-[0_12px_24px_rgba(3,33,71,0.08)]",
        "cursor-grab touch-none transition-all duration-150 active:cursor-grabbing",
        isDragging && "opacity-60 shadow-[0_18px_32px_rgba(3,33,71,0.16)]"
      )}
      {...attributes}
      {...listeners}
      data-testid={`card-${card.id}`}
    >
      {isEditing ? (
        <form onPointerDown={(event) => event.stopPropagation()} onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          if (!title.trim()) return;
          onEdit(card.id, title.trim(), details.trim());
          setIsEditing(false);
        }} className="space-y-3">
          <input aria-label="Card title" value={title} onChange={(event) => setTitle(event.target.value)} className="w-full rounded-xl border border-[var(--stroke)] px-3 py-2 text-sm" />
          <textarea aria-label="Card details" value={details} onChange={(event) => setDetails(event.target.value)} rows={3} className="w-full rounded-xl border border-[var(--stroke)] px-3 py-2 text-sm" />
          <div className="flex gap-2">
            <button type="submit" className="rounded-full bg-[var(--secondary-purple)] px-3 py-1 text-xs font-semibold text-white">Save</button>
            <button type="button" onClick={cancelEdit} className="rounded-full border border-[var(--stroke)] px-3 py-1 text-xs font-semibold">Cancel</button>
          </div>
        </form>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="font-display text-base font-semibold text-[var(--navy-dark)]">{card.title}</h4>
            <p className="mt-2 text-sm leading-6 text-[var(--gray-text)]">{card.details}</p>
          </div>
          <div className="flex shrink-0 gap-1" onPointerDown={(event) => event.stopPropagation()}>
            <button
              type="button"
              onClick={openEdit}
              title="Edit"
              className="rounded-full p-1.5 text-[var(--gray-text)] transition hover:bg-[var(--surface)] hover:text-[var(--primary-blue)]"
              aria-label={`Edit ${card.title}`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => onDelete(card.id)}
              title="Delete"
              className="rounded-full p-1.5 text-[var(--gray-text)] transition hover:bg-red-50 hover:text-red-600"
              aria-label={`Delete ${card.title}`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                <path d="M3 6h18" />
                <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6" />
                <path d="M14 11v6" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </article>
  );
};
