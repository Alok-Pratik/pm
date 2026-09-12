import type { BoardData } from "@/lib/kanban";

export type ChatResponse = {
  version: 1;
  message: string;
  board: BoardData;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

const requestBoard = async (input: RequestInfo, init?: RequestInit): Promise<BoardData> => {
  const response = await fetch(input, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(data?.detail || "The board request failed.", response.status);
  }

  return response.json() as Promise<BoardData>;
};

export const getBoard = () => requestBoard("/api/board");

export const renameColumn = (columnId: string, title: string) =>
  requestBoard(`/api/columns/${columnId}`, { method: "PUT", body: JSON.stringify({ title }) });

export const createCard = (columnId: string, title: string, details: string) =>
  requestBoard("/api/cards", { method: "POST", body: JSON.stringify({ column_id: columnId, title, details }) });

export const updateCard = (cardId: string, title: string, details: string) =>
  requestBoard(`/api/cards/${cardId}`, { method: "PATCH", body: JSON.stringify({ title, details }) });

export const deleteCard = (cardId: string) =>
  requestBoard(`/api/cards/${cardId}`, { method: "DELETE" });

export const moveCard = (cardId: string, columnId: string, position: number) =>
  requestBoard(`/api/cards/${cardId}/move`, { method: "POST", body: JSON.stringify({ column_id: columnId, position }) });

export const sendChat = async (message: string): Promise<ChatResponse> => {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(data?.detail || "The chat request failed.", response.status);
  }
  return response.json() as Promise<ChatResponse>;
};

export const getChatHistory = async (): Promise<ChatMessage[]> => {
  const response = await fetch("/api/chat/history");
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(data?.detail || "The chat history request failed.", response.status);
  }
  const data = (await response.json()) as { messages: ChatMessage[] };
  return data.messages;
};