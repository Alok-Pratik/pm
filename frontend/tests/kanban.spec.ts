import { expect, test } from "@playwright/test";

// Backend usernames are capped at 32 characters, so keep this well under that.
const uniqueUsername = (label: string) =>
  `p${label.slice(0, 6)}${Date.now().toString(36)}${Math.floor(Math.random() * 1000).toString(36)}`;

const registerAndOpenBoard = async (page: import("@playwright/test").Page, username: string) => {
  await page.goto("/");
  await page.getByRole("button", { name: /new here\? create an account/i }).click();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: /^create account$/i }).click();
  // A freshly registered user has exactly one board, so the app lands on it directly.
  await expect(page.getByRole("heading", { name: "My board" })).toBeVisible();
};

const currentBoardId = async (page: import("@playwright/test").Page): Promise<string> => {
  const response = await page.request.get("/api/boards");
  const data = await response.json();
  return data.boards[0].id;
};

test("registers a new account and lands on a five-column starter board", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("register"));
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
});

test("rejects registering the same username twice", async ({ page }) => {
  const username = uniqueUsername("dupe");
  await registerAndOpenBoard(page, username);
  await page.request.post("/api/auth/logout");
  await page.goto("/");
  await page.getByRole("button", { name: /new here\? create an account/i }).click();
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: /^create account$/i }).click();
  await expect(page.getByText(/already taken/i)).toBeVisible();
});

test("adds a card to a column", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("addcard"));
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  const title = `Playwright card ${Date.now()}`;
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill(title);
  await firstColumn.getByPlaceholder("Details").fill("Added via e2e.");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText(title, { exact: true })).toBeVisible();
});

test("moves a card between columns", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("movecard"));
  const boardId = await currentBoardId(page);
  const columns = page.locator('[data-testid^="column-"]');
  const sourceColumn = columns.nth(0); // Backlog
  const targetColumn = columns.nth(3); // Review
  const title = `Movable card ${Date.now()}`;
  await sourceColumn.getByRole("button", { name: /add a card/i }).click();
  await sourceColumn.getByPlaceholder("Card title").fill(title);
  await sourceColumn.getByRole("button", { name: /add card/i }).click();
  const card = sourceColumn.locator('[data-testid^="card-"]').filter({ hasText: title });
  const cardTestId = await card.getAttribute("data-testid");
  if (!cardTestId) throw new Error("Movable card did not have a test id.");
  const targetColumnId = await targetColumn.getAttribute("data-testid").then((id) => id?.replace(/^column-/, ""));
  if (!targetColumnId) throw new Error("Target column did not have a test id.");
  await card.scrollIntoViewIfNeeded();
  const cardId = cardTestId.replace(/^card-/, "");
  const response = await page.request.post(`/api/boards/${boardId}/cards/${cardId}/move`, {
    data: { column_id: targetColumnId, position: 0 },
  });
  expect(response.ok()).toBeTruthy();
  const movedBoard = await response.json();
  expect(movedBoard.columns.find((column: { id: string }) => column.id === targetColumnId).cardIds).toContain(cardId);
});

test("persists rename, edit, and delete operations", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("persist"));
  const firstColumn = page.locator('[data-testid^="column-"]').first();
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
  await expect(page.locator('[data-testid^="column-"]').first().getByLabel("Column title")).toHaveValue("Queued");
  await expect(page.getByText("Updated customer signals")).not.toBeVisible();
});

test("chat sidebar applies the canonical board response", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("chat"));
  const boardId = await currentBoardId(page);
  const boardResponse = await page.request.get(`/api/boards/${boardId}`);
  const board = await boardResponse.json();
  board.columns[0].title = "AI Ideas";

  await page.route(`**/api/boards/${boardId}/chat`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ version: 1, message: "I renamed the first column.", board }),
    });
  });

  await page.getByLabel("Message the AI assistant").fill("Rename the first column.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("I renamed the first column.")).toBeVisible();
  await expect(page.locator('[data-testid^="column-"]').first().getByLabel("Column title")).toHaveValue("AI Ideas");
});

test("keeps the board and chatbot usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await registerAndOpenBoard(page, uniqueUsername("mobile"));
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
  await expect(page.getByRole("complementary", { name: "AI assistant" })).toBeVisible();
  await expect(page.locator(".board-lane")).toHaveCSS("display", "flex");
});

// --- drag and drop ---

test("drag and drop reorders a card within a column via pointer events", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("dnd"));
  const discovery = page.locator('[data-testid^="column-"]').nth(1); // Discovery

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

  const boardId = await currentBoardId(page);
  const board = await page.request.get(`/api/boards/${boardId}`).then((r) => r.json());
  const discoveryColumnId = board.columns[1].id;
  const discoveryCol = board.columns.find((c: { id: string }) => c.id === discoveryColumnId);
  const aIndex = discoveryCol.cardIds.indexOf(cardAId);
  // Card A should have moved from its original position — the drag was registered
  expect(aIndex).toBeGreaterThan(-1);
  const allTitles: string[] = discoveryCol.cardIds.map((id: string) => board.cards[id]?.title ?? "");
  expect(allTitles.indexOf(titleB)).toBeLessThan(allTitles.indexOf(titleA));
});

// --- auth ---

test("shows an error message on invalid credentials", async ({ page }) => {
  const username = uniqueUsername("badlogin");
  await registerAndOpenBoard(page, username);
  await page.request.post("/api/auth/logout");
  await page.goto("/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("wrongpassword");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(/invalid credentials/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "My board" })).not.toBeVisible();
});

test("returns to login when session cookie is cleared", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("sessionexpiry"));
  await page.context().clearCookies();
  await page.reload();
  await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
});

// --- multi-board ---

test("creates a second board, switches between boards, and keeps data isolated", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("multiboard"));

  await page.getByRole("button", { name: /all boards/i }).click();
  await expect(page.getByRole("heading", { name: "Your boards" })).toBeVisible();
  await expect(page.getByRole("button", { name: "My board" })).toBeVisible();

  await page.getByLabel("New board title").fill("Marketing launch");
  await page.getByRole("button", { name: /create board/i }).click();
  // Creating a board opens it immediately rather than leaving you on the switcher.
  await expect(page.getByRole("heading", { name: "Marketing launch" })).toBeVisible();
  // A brand-new board starts with five empty columns, unlike the seeded starter board.
  await expect(page.locator('[data-testid^="card-"]')).toHaveCount(0);

  const title = `Marketing-only card ${Date.now()}`;
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill(title);
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText(title)).toBeVisible();

  await page.getByRole("button", { name: /all boards/i }).click();
  await page.getByRole("button", { name: "My board" }).click();
  await expect(page.getByRole("heading", { name: "My board" })).toBeVisible();
  await expect(page.getByText(title)).not.toBeVisible();
});

test("renaming and deleting a board updates the switcher", async ({ page }) => {
  await registerAndOpenBoard(page, uniqueUsername("boardmgmt"));
  await page.getByRole("button", { name: /all boards/i }).click();

  await page.getByLabel("New board title").fill("Temp board");
  await page.getByRole("button", { name: /create board/i }).click();
  // Creating a board opens it immediately; go back to the switcher to manage it.
  await expect(page.getByRole("heading", { name: "Temp board" })).toBeVisible();
  await page.getByRole("button", { name: /all boards/i }).click();
  await expect(page.getByRole("button", { name: "Temp board" })).toBeVisible();

  const row = page.getByRole("listitem").filter({ hasText: "Temp board" });
  await row.getByRole("button", { name: /rename/i }).click();
  const renameInput = page.getByLabel("Rename Temp board");
  await renameInput.fill("Renamed board");
  await renameInput.blur();
  await expect(page.getByRole("button", { name: "Renamed board" })).toBeVisible();

  await page.getByRole("listitem").filter({ hasText: "Renamed board" }).getByRole("button", { name: /delete/i }).click();
  await expect(page.getByRole("button", { name: "Renamed board" })).not.toBeVisible();
});
