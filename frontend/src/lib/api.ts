import type { BoardData, BoardSummary } from "@/lib/kanban";

export type ChatResponse = {
  version: 1;
  message: string;
  board: BoardData;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type AuthResponse = {
  authenticated: boolean;
  username?: string;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

// Calls onUnauthorized when reason is a 401 from the API; otherwise a no-op.
export const notifyIfUnauthorized = (reason: unknown, onUnauthorized?: () => void): void => {
  if (reason instanceof ApiError && reason.status === 401) {
    onUnauthorized?.();
  }
};

export const describeApiError = (reason: unknown, fallback: string): string =>
  reason instanceof Error ? reason.message : fallback;

const parseJsonOrThrow = async <T>(response: Response, fallbackMessage: string): Promise<T> => {
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(data?.detail || fallbackMessage, response.status);
  }
  return response.json() as Promise<T>;
};

const requestJson = async <T>(input: RequestInfo, init: RequestInit | undefined, fallbackMessage: string): Promise<T> => {
  const response = await fetch(input, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  return parseJsonOrThrow<T>(response, fallbackMessage);
};

const requestBoard = (input: RequestInfo, init?: RequestInit): Promise<BoardData> =>
  requestJson<BoardData>(input, init, "The board request failed.");

export const register = (username: string, password: string): Promise<AuthResponse> =>
  requestJson<AuthResponse>(
    "/api/auth/register",
    { method: "POST", body: JSON.stringify({ username, password }) },
    "Registration failed."
  );

export const login = (username: string, password: string): Promise<AuthResponse> =>
  requestJson<AuthResponse>(
    "/api/auth/login",
    { method: "POST", body: JSON.stringify({ username, password }) },
    "Invalid credentials."
  );

export const logout = (): Promise<AuthResponse> =>
  requestJson<AuthResponse>("/api/auth/logout", { method: "POST" }, "Sign out failed.");

export const getSession = (): Promise<AuthResponse> =>
  requestJson<AuthResponse>("/api/auth/session", undefined, "Session check failed.");

export const listBoards = async (): Promise<BoardSummary[]> => {
  const data = await requestJson<{ boards: BoardSummary[] }>(
    "/api/boards",
    undefined,
    "Could not load boards."
  );
  return data.boards;
};

export const createBoard = (title: string) =>
  requestBoard("/api/boards", { method: "POST", body: JSON.stringify({ title }) });

export const getBoard = (boardId: string) => requestBoard(`/api/boards/${boardId}`);

export const renameBoard = (boardId: string, title: string) =>
  requestBoard(`/api/boards/${boardId}`, { method: "PATCH", body: JSON.stringify({ title }) });

export const deleteBoard = async (boardId: string): Promise<BoardSummary[]> => {
  const data = await requestJson<{ boards: BoardSummary[] }>(
    `/api/boards/${boardId}`,
    { method: "DELETE" },
    "Could not delete board."
  );
  return data.boards;
};

export const renameColumn = (boardId: string, columnId: string, title: string) =>
  requestBoard(`/api/boards/${boardId}/columns/${columnId}`, { method: "PUT", body: JSON.stringify({ title }) });

export const createCard = (boardId: string, columnId: string, title: string, details: string) =>
  requestBoard(`/api/boards/${boardId}/cards`, { method: "POST", body: JSON.stringify({ column_id: columnId, title, details }) });

export const updateCard = (boardId: string, cardId: string, title: string, details: string) =>
  requestBoard(`/api/boards/${boardId}/cards/${cardId}`, { method: "PATCH", body: JSON.stringify({ title, details }) });

export const deleteCard = (boardId: string, cardId: string) =>
  requestBoard(`/api/boards/${boardId}/cards/${cardId}`, { method: "DELETE" });

export const moveCard = (boardId: string, cardId: string, columnId: string, position: number) =>
  requestBoard(`/api/boards/${boardId}/cards/${cardId}/move`, { method: "POST", body: JSON.stringify({ column_id: columnId, position }) });

export const sendChat = (boardId: string, message: string): Promise<ChatResponse> =>
  requestJson<ChatResponse>(
    `/api/boards/${boardId}/chat`,
    { method: "POST", body: JSON.stringify({ message }) },
    "The chat request failed."
  );

export const getChatHistory = async (boardId: string): Promise<ChatMessage[]> => {
  const data = await requestJson<{ messages: ChatMessage[] }>(
    `/api/boards/${boardId}/chat/history`,
    undefined,
    "The chat history request failed."
  );
  return data.messages;
};
