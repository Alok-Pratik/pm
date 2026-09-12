import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatSidebar } from "@/components/ChatSidebar";
import { ApiError } from "@/lib/api";

const { api } = vi.hoisted(() => ({
  api: {
    getChatHistory: vi.fn(),
    sendChat: vi.fn(),
  },
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return { ...original, ...api };
});

const mockBoard = { columns: [], cards: {} };

describe("ChatSidebar", () => {
  beforeEach(() => {
    api.getChatHistory.mockResolvedValue([]);
    api.sendChat.mockResolvedValue({ version: 1, message: "Board updated.", board: mockBoard });
  });

  it("shows placeholder when there are no messages", async () => {
    render(<ChatSidebar onBoardUpdate={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(/ask for a board update/i)).toBeInTheDocument()
    );
  });

  it("sends a message and displays the assistant reply", async () => {
    const onBoardUpdate = vi.fn();
    render(<ChatSidebar onBoardUpdate={onBoardUpdate} />);
    await waitFor(() => expect(api.getChatHistory).toHaveBeenCalled());

    await userEvent.type(screen.getByLabelText(/message the ai assistant/i), "Hello AI");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => expect(screen.getByText("Board updated.")).toBeInTheDocument());
    expect(onBoardUpdate).toHaveBeenCalledWith(mockBoard);
    expect(screen.getByText("Hello AI")).toBeInTheDocument();
  });

  it("removes the optimistic user message and shows an error on failure", async () => {
    api.sendChat.mockRejectedValue(new Error("Network error"));
    render(<ChatSidebar onBoardUpdate={vi.fn()} />);
    await waitFor(() => expect(api.getChatHistory).toHaveBeenCalled());

    await userEvent.type(screen.getByLabelText(/message the ai assistant/i), "Fail me");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText("Fail me")).not.toBeInTheDocument();
  });

  it("calls onUnauthorized on 401 during history load", async () => {
    api.getChatHistory.mockRejectedValue(new ApiError("Unauthorized", 401));
    const onUnauthorized = vi.fn();
    render(<ChatSidebar onBoardUpdate={vi.fn()} onUnauthorized={onUnauthorized} />);
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalled());
  });

  it("shows Sending state and re-enables after completion", async () => {
    let resolve: (v: unknown) => void;
    api.sendChat.mockImplementation(() => new Promise((r) => { resolve = r; }));
    render(<ChatSidebar onBoardUpdate={vi.fn()} />);
    await waitFor(() => expect(api.getChatHistory).toHaveBeenCalled());

    await userEvent.type(screen.getByLabelText(/message the ai assistant/i), "Hello");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));

    // While in-flight: button shows "Sending..." and is disabled
    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled();

    resolve!({ version: 1, message: "Done", board: mockBoard });

    // After completion: button returns to "Send message"
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /send message/i })).toBeInTheDocument()
    );
  });
});
