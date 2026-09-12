"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { BoardData } from "@/lib/kanban";
import { describeApiError, getChatHistory, notifyIfUnauthorized, sendChat, type ChatMessage } from "@/lib/api";

type ChatSidebarProps = {
  boardId: string;
  onBoardUpdate: (board: BoardData) => void;
  onUnauthorized?: () => void;
};

export const ChatSidebar = ({ boardId, onBoardUpdate, onUnauthorized }: ChatSidebarProps) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [message, setMessage] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setMessages([]);
    getChatHistory(boardId).then(setMessages).catch((reason) => {
      notifyIfUnauthorized(reason, onUnauthorized);
    });
  }, [boardId, onUnauthorized]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = message.trim();
    if (!content || isSending) return;

    setError("");
    setMessage("");
    setMessages((current) => [...current, { role: "user", content }]);
    setIsSending(true);
    try {
      const response = await sendChat(boardId, content);
      onBoardUpdate(response.board);
      setMessages((current) => [...current, { role: "assistant", content: response.message }]);
    } catch (reason) {
      notifyIfUnauthorized(reason, onUnauthorized);
      setMessages((current) => current.slice(0, -1));
      setError(describeApiError(reason, "The chat request failed."));
    } finally {
      setIsSending(false);
    }
  };

  return (
    <aside className="flex min-h-[520px] flex-col rounded-3xl border border-[var(--stroke)] bg-[var(--navy-dark)] p-5 text-white shadow-[var(--shadow)]" aria-label="AI assistant">
      <div className="flex items-start justify-between gap-4 border-b border-white/15 pb-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[var(--accent-yellow)]">AI assistant</p>
          <h2 className="mt-2 font-display text-2xl font-semibold">Board copilot</h2>
        </div>
        <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/70">Online</span>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto py-5" aria-live="polite">
        {messages.length === 0 && <p className="text-sm leading-6 text-white/60">Ask for a board update or a quick project summary.</p>}
        {messages.map((entry, index) => (
          <div key={`${entry.role}-${index}`} className={entry.role === "user" ? "ml-6 rounded-2xl bg-[var(--primary-blue)] p-3 text-sm" : "mr-6 rounded-2xl bg-white/10 p-3 text-sm text-white/85"}>
            {entry.content}
          </div>
        ))}
        {isSending && <p className="text-sm text-white/60">Thinking...</p>}
      </div>
      {error && <p role="alert" className="mb-3 rounded-xl bg-red-400/20 px-3 py-2 text-sm text-red-100">{error}</p>}
      <form onSubmit={handleSubmit} className="border-t border-white/15 pt-4">
        <label htmlFor="chat-message" className="sr-only">Message the AI assistant</label>
        <textarea
          id="chat-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Ask the board copilot..."
          rows={3}
          disabled={isSending}
          className="w-full resize-none rounded-2xl border border-white/15 bg-white/10 px-3 py-3 text-sm text-white outline-none placeholder:text-white/45 focus:border-[var(--accent-yellow)]"
        />
        <button type="submit" disabled={isSending || !message.trim()} className="mt-3 w-full rounded-full bg-[var(--accent-yellow)] px-4 py-3 text-sm font-semibold text-[var(--navy-dark)] disabled:cursor-not-allowed disabled:opacity-50">
          {isSending ? "Sending..." : "Send message"}
        </button>
      </form>
    </aside>
  );
};
