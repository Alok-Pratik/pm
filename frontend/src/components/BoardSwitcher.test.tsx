import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BoardSwitcher } from "@/components/BoardSwitcher";

const boards = [
  { id: "board-1", title: "Marketing" },
  { id: "board-2", title: "Engineering" },
];

describe("BoardSwitcher", () => {
  it("shows an empty state when there are no boards", () => {
    render(
      <BoardSwitcher
        boards={[]}
        onOpen={vi.fn()}
        onCreate={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText(/don't have any boards yet/i)).toBeInTheDocument();
  });

  it("lists boards and opens one on click", async () => {
    const onOpen = vi.fn();
    render(
      <BoardSwitcher
        boards={boards}
        onOpen={onOpen}
        onCreate={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "Marketing" }));
    expect(onOpen).toHaveBeenCalledWith("board-1");
  });

  it("creates a board from the form", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(
      <BoardSwitcher
        boards={boards}
        onOpen={vi.fn()}
        onCreate={onCreate}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    await userEvent.type(screen.getByLabelText("New board title"), "Design");
    await userEvent.click(screen.getByRole("button", { name: /create board/i }));
    expect(onCreate).toHaveBeenCalledWith("Design");
  });

  it("renames a board", async () => {
    const onRename = vi.fn().mockResolvedValue(undefined);
    render(
      <BoardSwitcher
        boards={boards}
        onOpen={vi.fn()}
        onCreate={vi.fn()}
        onRename={onRename}
        onDelete={vi.fn()}
      />
    );
    await userEvent.click(screen.getAllByRole("button", { name: /rename/i })[0]);
    const input = screen.getByLabelText("Rename Marketing");
    await userEvent.clear(input);
    await userEvent.type(input, "Growth");
    await userEvent.tab();
    await waitFor(() => expect(onRename).toHaveBeenCalledWith("board-1", "Growth"));
  });

  it("deletes a board", async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(
      <BoardSwitcher
        boards={boards}
        onOpen={vi.fn()}
        onCreate={vi.fn()}
        onRename={vi.fn()}
        onDelete={onDelete}
      />
    );
    await userEvent.click(screen.getAllByRole("button", { name: /delete/i })[0]);
    expect(onDelete).toHaveBeenCalledWith("board-1");
  });

  it("calls onLogout when the sign out button is used", async () => {
    const onLogout = vi.fn();
    render(
      <BoardSwitcher
        boards={boards}
        onOpen={vi.fn()}
        onCreate={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onLogout={onLogout}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(onLogout).toHaveBeenCalled();
  });

  it("shows an error message when provided", () => {
    render(
      <BoardSwitcher
        boards={boards}
        error="Could not load your boards."
        onOpen={vi.fn()}
        onCreate={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load your boards.");
  });
});
