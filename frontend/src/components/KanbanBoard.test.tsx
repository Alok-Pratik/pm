import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KanbanBoard } from "@/components/KanbanBoard";
import { initialData } from "@/test/fixtures";

const { api } = vi.hoisted(() => ({
  api: {
    getBoard: vi.fn(),
    getChatHistory: vi.fn(),
    renameColumn: vi.fn(),
    createCard: vi.fn(),
    updateCard: vi.fn(),
    deleteCard: vi.fn(),
    moveCard: vi.fn(),
  },
}));
const board = structuredClone(initialData);

vi.mock("@/lib/api", () => api);

const resetApi = () => {
  Object.assign(board, structuredClone(initialData));
  api.getBoard.mockImplementation(async () => structuredClone(board));
  api.getChatHistory.mockResolvedValue([]);
  api.renameColumn.mockImplementation(async (_boardId: string, columnId: string, title: string) => {
    board.columns = board.columns.map((column) => column.id === columnId ? { ...column, title } : column);
    return structuredClone(board);
  });
  api.createCard.mockImplementation(async (_boardId: string, columnId: string, title: string, details: string) => {
    const id = "card-test";
    board.cards[id] = { id, title, details: details || "No details yet." };
    board.columns = board.columns.map((column) => column.id === columnId ? { ...column, cardIds: [...column.cardIds, id] } : column);
    return structuredClone(board);
  });
  api.deleteCard.mockImplementation(async (_boardId: string, cardId: string) => {
    delete board.cards[cardId];
    board.columns = board.columns.map((column) => ({ ...column, cardIds: column.cardIds.filter((id) => id !== cardId) }));
    return structuredClone(board);
  });
};

const getFirstColumn = () => screen.getAllByTestId(/column-/i)[0];

describe("KanbanBoard", () => {
  beforeEach(resetApi);

  it("renders five columns", () => {
    render(<KanbanBoard boardId="board-test" />);
    return waitFor(() => expect(screen.getAllByTestId(/column-/i)).toHaveLength(5));
  });

  it("loads the given board id", () => {
    render(<KanbanBoard boardId="board-test" />);
    return waitFor(() => expect(api.getBoard).toHaveBeenCalledWith("board-test"));
  });

  it("renames a column", async () => {
    render(<KanbanBoard boardId="board-test" />);
    await waitFor(() => expect(screen.getAllByTestId(/column-/i)).toHaveLength(5));
    const column = getFirstColumn();
    const input = within(column).getByLabelText("Column title");
    await userEvent.clear(input);
    await userEvent.type(input, "New Name");
    expect(input).toHaveValue("New Name");
    await userEvent.tab();
    await waitFor(() => expect(api.renameColumn).toHaveBeenCalledWith("board-test", "col-backlog", "New Name"));
  });

  it("adds and removes a card", async () => {
    render(<KanbanBoard boardId="board-test" />);
    await waitFor(() => expect(screen.getAllByTestId(/column-/i)).toHaveLength(5));
    const column = getFirstColumn();
    const addButton = within(column).getByRole("button", {
      name: /add a card/i,
    });
    await userEvent.click(addButton);

    const titleInput = within(column).getByPlaceholderText(/card title/i);
    await userEvent.type(titleInput, "New card");
    const detailsInput = within(column).getByPlaceholderText(/details/i);
    await userEvent.type(detailsInput, "Notes");

    await userEvent.click(within(column).getByRole("button", { name: /add card/i }));

    expect(within(column).getByText("New card")).toBeInTheDocument();

    const deleteButton = within(column).getByRole("button", {
      name: /delete new card/i,
    });
    await userEvent.click(deleteButton);

    expect(within(column).queryByText("New card")).not.toBeInTheDocument();
  });

  it("shows an 'All boards' button that calls onBack", async () => {
    const onBack = vi.fn();
    render(<KanbanBoard boardId="board-test" onBack={onBack} />);
    await waitFor(() => expect(screen.getAllByTestId(/column-/i)).toHaveLength(5));
    await userEvent.click(screen.getByRole("button", { name: /all boards/i }));
    expect(onBack).toHaveBeenCalled();
  });
});
