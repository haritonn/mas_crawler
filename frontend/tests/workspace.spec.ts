import { test, expect } from "@playwright/test";

test("evaluation empty action is below its description on desktop and mobile", async ({
  page,
}) => {
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/#evaluation");
    const empty = page.locator(".empty-state");
    await expect(
      empty.getByRole("heading", { name: "Сначала — эталонная разметка" }),
    ).toBeVisible();
    await expect(empty.locator("p button")).toHaveCount(0);
    const description = await empty.locator("p").boundingBox();
    const action = await empty
      .getByRole("button", { name: "Перейти к разметке" })
      .boundingBox();
    expect(action!.y).toBeGreaterThanOrEqual(
      description!.y + description!.height + 16,
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
});

test("real local workflow: browse, search, save, resume, accept, evaluate, export", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Хороший поиск начинается с данных." }),
  ).toBeVisible();
  await expect(page.locator(".source-card")).toHaveCount(2);
  await page.locator(".source-card").filter({ hasText: "browser-fixture" }).click();
  await page.getByRole("button", { name: "Новый запуск" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("Адрес сайта").fill("https://example.test");
  await page.getByLabel("Цель сбора").fill("Проверка без запуска сети");
  await page.getByLabel("Число пар").fill("2");
  expect(
    await page
      .getByLabel("Число пар")
      .evaluate((element: HTMLInputElement) => element.validity.rangeUnderflow),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();

  await page.getByRole("button", { name: "Поиск", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Поисковый запрос" })
    .fill("std::ffi CStr");
  await page.getByRole("button", { name: "Найти", exact: true }).click();
  await expect(page.locator(".search-result")).toHaveCount(1);
  await expect(page.locator(".result-content h3")).toContainText("CStr");
  await page.getByRole("button", { name: "Читать фрагмент" }).click();
  await expect(page.locator(".result-excerpt")).toHaveClass(/expanded/);

  await page
    .getByRole("button", { name: "Разметка", exact: false })
    .first()
    .click();
  await expect(page.locator(".reader-panel")).toBeVisible();
  const waitSave = () =>
    page.waitForResponse(
      (response) =>
        response.request().method() === "PATCH" &&
        response.url().includes("/pairs/"),
    );
  let response = waitSave();
  await page.locator(".grade-button").nth(3).click();
  expect((await response).ok()).toBeTruthy();
  await page.reload();
  await expect(page.locator(".annotation-progress")).toContainText("1");
  for (const grade of [0, 0, 3]) {
    response = waitSave();
    await page.locator(".grade-button").nth(grade).click();
    expect((await response).ok()).toBeTruthy();
    await expect(page.locator(".save-state")).toContainText(
      "Все изменения сохранены",
    );
  }
  await expect(
    page.getByRole("button", { name: "Принять разметку" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Принять разметку" }).click();
  await page.getByRole("button", { name: "Да, зафиксировать" }).click();
  await expect(
    page.getByRole("button", { name: "К оценке поиска" }),
  ).toBeVisible();
  const exported = await page.request.get(
    "/api/runs/browser-fixture/export?package=annotation",
  );
  expect(exported.ok()).toBeTruthy();
  expect(await exported.text()).toContain("relevance");
  const accepted = await page.request.patch(
    "/api/runs/browser-fixture/pairs/p1?package=annotation",
    { data: { relevance: 0 } },
  );
  expect(accepted.status()).toBe(409);
  await page.getByRole("button", { name: "К оценке поиска" }).click();
  await page.getByRole("button", { name: "Запустить сравнение" }).click();
  await expect(page.locator(".metrics-grid")).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await expect(page.locator(".per-query")).toContainText("nDCG");
  expect(errors).toEqual([]);
});

test("mobile layout, keyboard navigation and no horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".source-card").first()).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Разметка", exact: false })
    .first()
    .click();
  await expect(page.locator(".reader-panel")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveCount(1);
});

test("overview links open sources, corpus documents and annotation", async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.source-card')).toHaveCount(2);
  await expect(page.locator('.workspace-label, .sidebar-note')).toHaveCount(0);
  const colors = await page.locator('.stat').evaluateAll(items => items.map(item => getComputedStyle(item).backgroundColor));
  expect(new Set(colors).size).toBe(3);
  await page.getByRole('link', { name: /Источников/ }).click();
  await expect(page).toHaveURL(/#sources$/);
  await expect(page.locator('.source-record')).toHaveCount(2);
  await page.getByRole('button', { name: 'Обзор', exact: true }).click();
  await page.getByRole('link', { name: /Документов/ }).click();
  await page.getByLabel('Выбрать источник').selectOption('browser-fixture');
  await expect(page.locator('.corpus-document')).toHaveCount(2);
  await page.getByLabel('Фильтр документов').fill('CStr');
  await page.locator('.document-filter').getByRole('button', { name: 'Найти' }).click();
  await expect(page.locator('.corpus-document')).toHaveCount(1);
  await page.getByRole('button', { name: 'Показать текст' }).click();
  await expect(page.locator('.corpus-excerpt')).toHaveClass(/expanded/);
  await page.getByRole('button', { name: 'Обзор', exact: true }).click();
  await page.getByRole('link', { name: /Размечено пар/ }).click();
  await expect(page.locator('.reader-panel')).toBeVisible();
});

test("source lifecycle is persistent and destructive actions require confirmation", async ({ page }) => {
  await page.goto('/#sources');
  await page.getByRole('button', { name: 'Переименовать management-fixture', exact: true }).click();
  await page.getByLabel('Название источника').fill('Мой тестовый корпус');
  await page.getByRole('button', { name: 'Сохранить название' }).click();
  await expect(page.getByRole('heading', { name: 'Мой тестовый корпус' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Мой тестовый корпус' })).toBeVisible();
  await page.getByRole('button', { name: 'Убрать из списка management-fixture', exact: true }).click();
  await expect(page.locator('.source-record')).toHaveCount(1);
  await page.getByRole('button', { name: /Убранные/ }).click();
  await expect(page.locator('.source-record')).toHaveCount(1);
  await page.getByRole('button', { name: 'Восстановить management-fixture', exact: true }).click();
  await expect(page.locator('.source-record')).toHaveCount(0);
  await page.getByRole('button', { name: /Активные/ }).click();
  const record = page.locator('.source-record').filter({ hasText: 'Мой тестовый корпус' });
  await record.getByRole('button', { name: 'Состав', exact: true }).click();
  await record.getByRole('button', { name: 'Удалить Поисковый индекс', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Удалить безвозвратно' })).toBeDisabled();
  await page.getByLabel('ID источника').fill('wrong-id');
  await expect(page.getByRole('button', { name: 'Удалить безвозвратно' })).toBeDisabled();
  await page.getByLabel('ID источника').fill('management-fixture');
  await page.getByRole('button', { name: 'Удалить безвозвратно' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  const response = await page.request.get('/api/runs/management-fixture');
  const run = await response.json();
  expect(run.components).toMatchObject({ corpus: true, index: false });
  expect(run.packages).toHaveLength(1);
  await page.getByRole('button', { name: 'Удалить всю цепочку management-fixture', exact: true }).click();
  await page.getByLabel('ID источника').fill('management-fixture');
  await page.getByRole('button', { name: 'Удалить безвозвратно' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.locator('.source-record')).toHaveCount(1);
  expect((await page.request.get('/api/runs/management-fixture')).status()).toBe(404);
  expect((await page.request.get('/api/runs/browser-fixture')).status()).toBe(200);
});
