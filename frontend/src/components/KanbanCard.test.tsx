import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KanbanCard } from "@/components/KanbanCard";
import type { Card } from "@/lib/kanban";

const card: Card = { id: "card-1", title: "Test Card", details: "Test details" };

describe("KanbanCard", () => {
  it("displays card title and details", () => {
    render(<KanbanCard card={card} onDelete={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText("Test Card")).toBeInTheDocument();
    expect(screen.getByText("Test details")).toBeInTheDocument();
  });

  it("opens edit form with current prop values", async () => {
    render(<KanbanCard card={card} onDelete={vi.fn()} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /edit test card/i }));
    expect(screen.getByLabelText("Card title")).toHaveValue("Test Card");
    expect(screen.getByLabelText("Card details")).toHaveValue("Test details");
  });

  it("syncs edit form to updated prop values after external board change", async () => {
    const { rerender } = render(<KanbanCard card={card} onDelete={vi.fn()} onEdit={vi.fn()} />);
    const updated: Card = { ...card, title: "AI-updated title", details: "New details" };
    rerender(<KanbanCard card={updated} onDelete={vi.fn()} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /edit ai-updated title/i }));
    expect(screen.getByLabelText("Card title")).toHaveValue("AI-updated title");
    expect(screen.getByLabelText("Card details")).toHaveValue("New details");
  });

  it("cancel resets dirty edit state to current prop values", async () => {
    render(<KanbanCard card={card} onDelete={vi.fn()} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /edit test card/i }));
    await userEvent.clear(screen.getByLabelText("Card title"));
    await userEvent.type(screen.getByLabelText("Card title"), "Dirty value");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: /edit test card/i }));
    expect(screen.getByLabelText("Card title")).toHaveValue("Test Card");
  });

  it("calls onEdit with trimmed values on save", async () => {
    const onEdit = vi.fn();
    render(<KanbanCard card={card} onDelete={vi.fn()} onEdit={onEdit} />);
    await userEvent.click(screen.getByRole("button", { name: /edit test card/i }));
    await userEvent.clear(screen.getByLabelText("Card title"));
    await userEvent.type(screen.getByLabelText("Card title"), "  Updated  ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onEdit).toHaveBeenCalledWith("card-1", "Updated", "Test details");
  });

  it("does not submit when title is blank", async () => {
    const onEdit = vi.fn();
    render(<KanbanCard card={card} onDelete={vi.fn()} onEdit={onEdit} />);
    await userEvent.click(screen.getByRole("button", { name: /edit test card/i }));
    await userEvent.clear(screen.getByLabelText("Card title"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("calls onDelete when Remove is clicked", async () => {
    const onDelete = vi.fn();
    render(<KanbanCard card={card} onDelete={onDelete} onEdit={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /delete test card/i }));
    expect(onDelete).toHaveBeenCalledWith("card-1");
  });
});
