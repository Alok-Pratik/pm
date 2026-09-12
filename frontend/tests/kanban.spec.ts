import { expect, test } from "@playwright/test";

const signIn = async (page: import("@playwright/test").Page) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
};

test("loads the kanban board", async ({ page }) => {
  await signIn(page);
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
});

test("adds a card to a column", async ({ page }) => {
  await signIn(page);
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  const title = `Playwright card ${Date.now()}`;
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill(title);
  await firstColumn.getByPlaceholder("Details").fill("Added via e2e.");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText(title, { exact: true })).toBeVisible();
});

test("moves a card between columns", async ({ page }) => {
  await signIn(page);
  const sourceColumn = page.getByTestId("column-col-backlog");
  const title = `Movable card ${Date.now()}`;
  await sourceColumn.getByRole("button", { name: /add a card/i }).click();
  await sourceColumn.getByPlaceholder("Card title").fill(title);
  await sourceColumn.getByRole("button", { name: /add card/i }).click();
  const card = sourceColumn.locator('[data-testid^="card-"]').filter({ hasText: title });
  const cardTestId = await card.getAttribute("data-testid");
  if (!cardTestId) throw new Error("Movable card did not have a test id.");
  await card.scrollIntoViewIfNeeded();
  const targetColumn = page.getByTestId("column-col-review");
  await targetColumn.scrollIntoViewIfNeeded();
  const cardId = cardTestId.replace(/^card-/, "");
  const response = await page.request.post(`/api/cards/${cardId}/move`, {
    data: { column_id: "col-review", position: 0 },
  });
  expect(response.ok()).toBeTruthy();
  const movedBoard = await response.json();
  expect(movedBoard.columns.find((column: { id: string }) => column.id === "col-review").cardIds).toContain(cardId);
});

test("persists rename, edit, and delete operations", async ({ page }) => {
  await signIn(page);
  const firstColumn = page.getByTestId("column-col-backlog");
  const titleInput = firstColumn.getByLabel("Column title");
  await titleInput.fill("Queued");
  await titleInput.blur();
  await expect(titleInput).toHaveValue("Queued");

  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Browser persistence card");
  await firstColumn.getByPlaceholder("Details").fill("Created for persistence coverage.");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  const card = firstColumn.getByTestId(/^card-/).filter({ hasText: "Browser persistence card" });
  await expect(card).toBeVisible();
  const cardTestId = await card.getAttribute("data-testid");
  if (!cardTestId) throw new Error("Created card did not have a test id.");
  const persistedCard = page.getByTestId(cardTestId);
  await persistedCard.getByRole("button", { name: /edit browser persistence card/i }).click();
  await persistedCard.getByLabel("Card title").fill("Updated customer signals");
  await persistedCard.getByLabel("Card details").fill("Updated from the browser.");
  await persistedCard.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Updated customer signals")).toBeVisible();

  await persistedCard.getByRole("button", { name: /delete updated customer signals/i }).click();
  await expect(persistedCard).not.toBeVisible();

  await page.reload();
  await expect(page.getByTestId("column-col-backlog").getByLabel("Column title")).toHaveValue("Queued");
  await expect(page.getByText("Updated customer signals")).not.toBeVisible();
});

test("moves the Review card between columns", async ({ page }) => {
  await signIn(page);
  const sourceColumn = page.getByTestId("column-col-review");
  const title = `Review movable card ${Date.now()}`;
  await sourceColumn.getByRole("button", { name: /add a card/i }).click();
  await sourceColumn.getByPlaceholder("Card title").fill(title);
  await sourceColumn.getByRole("button", { name: /add card/i }).click();
  const card = sourceColumn.locator('[data-testid^="card-"]').filter({ hasText: title });
  const cardTestId = await card.getAttribute("data-testid");
  if (!cardTestId) throw new Error("Review card did not have a test id.");
  await card.scrollIntoViewIfNeeded();
  const movedCardId = cardTestId.replace(/^card-/, "");
  const response = await page.request.post(`/api/cards/${movedCardId}/move`, {
    data: { column_id: "col-backlog", position: 0 },
  });
  expect(response.ok()).toBeTruthy();
  const movedBoard = await response.json();
  expect(movedBoard.columns.find((column: { id: string }) => column.id === "col-backlog").cardIds).toContain(movedCardId);
});

test("chat sidebar applies the canonical board response", async ({ page }) => {
  await signIn(page);
  const boardResponse = await page.request.get("/api/board");
  const board = await boardResponse.json();
  board.columns[0].title = "AI Ideas";

  await page.route("**/api/chat**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ version: 1, message: "I renamed the first column.", board }),
    });
  });

  await page.getByLabel("Message the AI assistant").fill("Rename the first column.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("I renamed the first column.")).toBeVisible();
  await expect(page.getByTestId("column-col-backlog").getByLabel("Column title")).toHaveValue("AI Ideas");
});

test("keeps the board and chatbot usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
  await expect(page.getByRole("complementary", { name: "AI assistant" })).toBeVisible();
  await expect(page.locator(".board-lane")).toHaveCSS("display", "flex");
});
