"use client";

import { useCallback, useEffect, useState } from "react";
import { BoardSwitcher } from "@/components/BoardSwitcher";
import { KanbanBoard } from "@/components/KanbanBoard";
import { ApiError, createBoard, deleteBoard, listBoards, renameBoard } from "@/lib/api";
import type { BoardSummary } from "@/lib/kanban";

type DashboardProps = {
  onLogout: () => void;
  onUnauthorized: () => void;
};

export const Dashboard = ({ onLogout, onUnauthorized }: DashboardProps) => {
  const [boards, setBoards] = useState<BoardSummary[] | null>(null);
  const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const handleFailure = useCallback(
    (reason: unknown, fallback: string) => {
      if (reason instanceof ApiError && reason.status === 401) {
        onUnauthorized();
        return;
      }
      setError(reason instanceof Error ? reason.message : fallback);
    },
    [onUnauthorized]
  );

  const refreshBoards = useCallback(async (preferredId?: string) => {
    try {
      const list = await listBoards();
      setBoards(list);
      setSelectedBoardId((current) => {
        if (preferredId && list.some((board) => board.id === preferredId)) return preferredId;
        if (current && list.some((board) => board.id === current)) return current;
        return null;
      });
    } catch (reason) {
      handleFailure(reason, "Could not load your boards.");
    }
  }, [handleFailure]);

  useEffect(() => {
    listBoards()
      .then((list) => {
        setBoards(list);
        setSelectedBoardId((current) => {
          if (current && list.some((board) => board.id === current)) return current;
          // Land straight on the board when there is only one — matches the
          // original single-board experience for a freshly registered user.
          return list.length === 1 ? list[0].id : null;
        });
      })
      .catch((reason) => handleFailure(reason, "Could not load your boards."));
  }, [handleFailure]);

  const handleCreate = async (title: string) => {
    setError("");
    try {
      const created = await createBoard(title);
      await refreshBoards(created.id);
    } catch (reason) {
      handleFailure(reason, "Could not create the board.");
    }
  };

  const handleRename = async (boardId: string, title: string) => {
    setError("");
    try {
      await renameBoard(boardId, title);
      // Renaming from the switcher should refresh the list in place, not
      // navigate into the board the way creating one does.
      await refreshBoards();
    } catch (reason) {
      handleFailure(reason, "Could not rename the board.");
    }
  };

  const handleDelete = async (boardId: string) => {
    setError("");
    try {
      const remaining = await deleteBoard(boardId);
      setBoards(remaining);
      setSelectedBoardId((current) => (current === boardId ? null : current));
    } catch (reason) {
      handleFailure(reason, "Could not delete the board.");
    }
  };

  if (boards === null) {
    return <main className="grid min-h-screen place-items-center p-6">{error ? <p role="alert">{error}</p> : <p>Loading your boards...</p>}</main>;
  }

  if (selectedBoardId) {
    return (
      <KanbanBoard
        boardId={selectedBoardId}
        onBack={() => setSelectedBoardId(null)}
        onLogout={onLogout}
        onUnauthorized={onUnauthorized}
      />
    );
  }

  return (
    <BoardSwitcher
      boards={boards}
      error={error}
      onOpen={setSelectedBoardId}
      onCreate={handleCreate}
      onRename={handleRename}
      onDelete={handleDelete}
      onLogout={onLogout}
    />
  );
};
