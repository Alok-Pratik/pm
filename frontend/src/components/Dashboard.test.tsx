import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dashboard } from "@/components/Dashboard";
import { ApiError } from "@/lib/api";

const { api } = vi.hoisted(() => ({
  api: {
    listBoards: vi.fn(),
    createBoard: vi.fn(),
    renameBoard: vi.fn(),
    deleteBoard: vi.fn(),
  },
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return { ...original, ...api };
});

vi.mock("@/components/KanbanBoard", () => ({
  KanbanBoard: ({ boardId, onBack }: { boardId: string; onBack?: () => void }) => (
    <div>
      <h1>Board {boardId}</h1>
      {onBack && <button type="button" onClick={onBack}>All boards</button>}
    </div>
  ),
}));

const boards = [
  { id: "board-1", title: "Marketing" },
  { id: "board-2", title: "Engineering" },
];

describe("Dashboard", () => {
  beforeEach(() => {
    api.listBoards.mockResolvedValue(boards);
  });

  it("shows the board switcher when there are multiple boards", async () => {
    render(<Dashboard onLogout={vi.fn()} onUnauthorized={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Marketing")).toBeInTheDocument());
    expect(screen.getByText("Engineering")).toBeInTheDocument();
  });

  it("lands directly on the board when the user has only one", async () => {
    api.listBoards.mockResolvedValue([boards[0]]);
    render(<Dashboard onLogout={vi.fn()} onUnauthorized={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Board board-1")).toBeInTheDocument());
  });

  it("opens a board and can go back to the switcher", async () => {
    render(<Dashboard onLogout={vi.fn()} onUnauthorized={vi.fn()} />);
    await waitFor(() => screen.getByText("Marketing"));

    await userEvent.click(screen.getByRole("button", { name: "Marketing" }));
    await waitFor(() => expect(screen.getByText("Board board-1")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /all boards/i }));
    await waitFor(() => expect(screen.getByText("Marketing")).toBeInTheDocument());
  });

  it("creates a board and opens it", async () => {
    api.createBoard.mockResolvedValue({ id: "board-3", title: "Design", columns: [], cards: {} });
    api.listBoards.mockResolvedValueOnce(boards).mockResolvedValueOnce([...boards, { id: "board-3", title: "Design" }]);
    render(<Dashboard onLogout={vi.fn()} onUnauthorized={vi.fn()} />);
    await waitFor(() => screen.getByText("Marketing"));

    await userEvent.type(screen.getByLabelText("New board title"), "Design");
    await userEvent.click(screen.getByRole("button", { name: /create board/i }));

    expect(api.createBoard).toHaveBeenCalledWith("Design");
    await waitFor(() => expect(screen.getByText("Board board-3")).toBeInTheDocument());
  });

  it("renaming a board from the switcher does not navigate into it", async () => {
    api.renameBoard.mockResolvedValue({ id: "board-1", title: "Growth", columns: [], cards: {} });
    api.listBoards.mockResolvedValueOnce(boards).mockResolvedValueOnce([{ id: "board-1", title: "Growth" }, boards[1]]);
    render(<Dashboard onLogout={vi.fn()} onUnauthorized={vi.fn()} />);
    await waitFor(() => screen.getByText("Marketing"));

    await userEvent.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByLabelText("Rename Marketing");
    await userEvent.clear(input);
    await userEvent.type(input, "Growth");
    await userEvent.tab();

    await waitFor(() => expect(api.renameBoard).toHaveBeenCalledWith("board-1", "Growth"));
    expect(screen.queryByText(/^Board board-1$/)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Growth")).toBeInTheDocument());
  });

  it("deletes a board and returns to the switcher list", async () => {
    api.deleteBoard.mockResolvedValue([boards[1]]);
    render(<Dashboard onLogout={vi.fn()} onUnauthorized={vi.fn()} />);
    await waitFor(() => screen.getByText("Marketing"));

    await userEvent.click(screen.getAllByRole("button", { name: /delete/i })[0]);

    await waitFor(() => expect(screen.queryByText("Marketing")).not.toBeInTheDocument());
    expect(screen.getByText("Engineering")).toBeInTheDocument();
  });

  it("calls onUnauthorized when loading boards returns 401", async () => {
    api.listBoards.mockRejectedValue(new ApiError("Unauthorized", 401));
    const onUnauthorized = vi.fn();
    render(<Dashboard onLogout={vi.fn()} onUnauthorized={onUnauthorized} />);
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalled());
  });
});
