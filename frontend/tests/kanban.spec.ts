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

// --- drag and drop (#16) ---

test("drag and drop reorders a card within a column via pointer events", async ({ page }) => {
  await signIn(page);

  // Use col-discovery: unmodified by other tests in this suite, starts with one seed card.
  // Add two fresh cards so we have full control over the initial order.
  const discovery = page.getByTestId("column-col-discovery");

  const titleA = `DnD card A ${Date.now()}`;
  const titleB = `DnD card B ${Date.now() + 1}`;

  await discovery.getByRole("button", { name: /add a card/i }).click();
  await discovery.getByPlaceholder("Card title").fill(titleA);
  await discovery.getByRole("button", { name: /add card/i }).click();
  await expect(discovery.getByText(titleA)).toBeVisible();

  await discovery.getByRole("button", { name: /add a card/i }).click();
  await discovery.getByPlaceholder("Card title").fill(titleB);
  await discovery.getByRole("button", { name: /add card/i }).click();
  await expect(discovery.getByText(titleB)).toBeVisible();

  const cardA = discovery.locator('[data-testid^="card-"]').filter({ hasText: titleA });
  const cardB = discovery.locator('[data-testid^="card-"]').filter({ hasText: titleB });
  const cardAId = (await cardA.getAttribute("data-testid"))?.replace("card-", "");
  if (!cardAId) throw new Error("Card A has no test id");

  const boxA = await cardA.boundingBox();
  const boxB = await cardB.boundingBox();
  if (!boxA || !boxB) throw new Error("Card bounding box not found");

  // Drag card A (above B) down past card B
  const startX = boxA.x + boxA.width / 2;
  const startY = boxA.y + boxA.height / 2;
  const endX = boxB.x + boxB.width / 2;
  const endY = boxB.y + boxB.height * 0.85;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX, startY + 10, { steps: 3 });
  await page.mouse.move(endX, endY, { steps: 20 });
  await page.mouse.up();

  // Allow the API move call to complete
  await page.waitForTimeout(600);

  const board = await page.request.get("/api/board").then((r) => r.json());
  const discoveryCol = board.columns.find((c: { id: string }) => c.id === "col-discovery");
  const aIndex = discoveryCol.cardIds.indexOf(cardAId);
  // Card A should have moved from its original position — the drag was registered
  expect(aIndex).toBeGreaterThan(-1);
  const allTitles: string[] = discoveryCol.cardIds.map((id: string) => board.cards[id]?.title ?? "");
  expect(allTitles.indexOf(titleB)).toBeLessThan(allTitles.indexOf(titleA));
});

// --- failed login and session expiry (#20) ---

test("shows an error message on invalid credentials", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("wrongpassword");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(/use user and password/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).not.toBeVisible();
});

test("returns to login when session cookie is cleared", async ({ page }) => {
  await signIn(page);
  await page.context().clearCookies();
  await page.reload();
  await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
});
