import { test, expect, Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const image = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='300'%3E%3Crect width='220' height='300' fill='gray'/%3E%3C/svg%3E";
const legacy = JSON.parse(readFileSync(new URL("../../data/museum.json", import.meta.url), "utf8"))
    .filter(item => item.type === "fichas/antiguas");
const archive = [
    ...legacy,
    { id: "old", name: "Canonical old card", category: "carta_vieja", image_url: image },
    { id: "new", name: "Canonical new card", category: "carta_nueva", image_url: image },
    { id: "label", name: "Canonical label", category: "etiquetas", image_url: image },
    { id: "archived-table", name: "Archived unavailable beer", category: "tap_list", type: "tap", source_beer_id: 77, image_url: image },
    { id: "table-2", name: "Historical table two", type: "tap_list", image_url: image },
    { id: "table-3", name: "Historical table three", category: "tap_list", image_url: image },
    { id: "other", name: "Packaging outside collections", category: "packaging", type: "fichas/antiguas", image_url: image },
];
const cards = (page: Page) => page.locator("[data-atlas-museum-card]");
const card = (page: Page, id: string) => page.locator(`[data-atlas-museum-card-id="${id}"]`);

async function mockArchive(page: Page, records = archive) {
    await page.route("**/api/public/museum", route => route.fulfill({ json: records }));
    await page.route("**/api/public/tap", route => route.fulfill({ json: [
        { id: 900, name: "Operational beer only", brewery: "Test", style: "IPA", abv: 5,
          is_available: true, tap_position: 1, image_url: image },
    ] }));
    await page.route("**/static/museum/**", route => route.fulfill({
        contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="300"><rect width="220" height="300" fill="gray"/></svg>',
    }));
}

test("four collections use archive categories, preserve legacy cards and never mix operational beers", async ({ page }) => {
    await mockArchive(page);
    await page.goto("/museum");
    const buttons = page.locator("[data-atlas-museum-selector]").getByRole("button");
    await expect(buttons).toHaveCount(4);
    for (const [index, label] of ["Tablas", "Cartas Viejas", "Cartas Nuevas", "Etiquetas"].entries()) {
        await expect(buttons.nth(index)).toHaveAccessibleName(label);
    }
    await expect(cards(page)).toHaveCount(legacy.length + 1);
    for (const item of legacy) await expect(card(page, item.id)).toHaveCount(1);
    for (const [label, ids] of [
        ["Tablas", ["archived-table", "table-2", "table-3"]],
        ["Cartas Nuevas", ["new"]], ["Etiquetas", ["label"]],
        ["Cartas Viejas", [...legacy.map(item => item.id), "old"]],
    ] as [string, string[]][]) {
        await page.getByRole("button", { name: label, exact: true }).click();
        await expect(cards(page)).toHaveCount(ids.length);
        for (const id of ids) await expect(card(page, id)).toHaveCount(1);
        await expect(page.getByRole("button", { name: label, exact: true })).toHaveAttribute("aria-pressed", "true");
        await expect(card(page, "900")).toHaveCount(0);
        await expect(card(page, "other")).toHaveCount(0);
    }
});

test("an unavailable beer's archived table remains visible independently of the operational response", async ({ page }) => {
    await mockArchive(page);
    await page.unroute("**/api/public/tap");
    await page.route("**/api/public/tap", route => route.fulfill({ json: [] }));
    await page.goto("/museum");
    await page.getByRole("button", { name: "Tablas", exact: true }).click();
    await expect(card(page, "archived-table")).toBeVisible();
    await expect(cards(page)).toHaveCount(3);
});

test("empty collections retain navigation and can return to existing artwork", async ({ page }) => {
    await mockArchive(page, legacy);
    await page.goto("/museum");
    await expect(cards(page)).toHaveCount(legacy.length);
    await page.getByRole("button", { name: "Etiquetas", exact: true }).click();
    await expect(cards(page)).toHaveCount(0);
    await expect(page.getByRole("status")).toHaveText("Esta colección todavía no tiene obras.");
    await page.getByRole("button", { name: "Cartas Viejas", exact: true }).click();
    await expect(cards(page)).toHaveCount(legacy.length);
});

test("an entirely empty archive and an invalid API response do not break navigation", async ({ page }) => {
    await mockArchive(page, []);
    await page.goto("/museum");
    await expect(page.getByRole("status")).toHaveText("Esta colección todavía no tiene obras.");
    await expect(page.locator("[data-atlas-museum-selector] button")).toHaveCount(4);
    await page.unroute("**/api/public/museum");
    await page.route("**/api/public/museum", route => route.fulfill({ json: { error: "bad payload" } }));
    await page.reload();
    await expect(page.getByRole("alert")).toHaveText("No se pudo cargar el archivo del Museo.");
    await expect(page.locator("[data-atlas-museum-selector] button")).toHaveCount(4);
});

for (const viewport of [{ width: 1280, height: 720 }, { width: 390, height: 844 }]) {
    test(`existing viewer and vertical dismiss gesture work at ${viewport.width}×${viewport.height}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await mockArchive(page, legacy.slice(0, 1));
        await page.goto("/museum");
        const artwork = card(page, legacy[0].id);
        // Existing behavior: first click centers an off-center card, next click opens it.
        await artwork.click();
        const overlay = page.locator("[data-atlas-museum-artwork-overlay]");
        if (await overlay.count() === 0) {
            await expect.poll(async () => artwork.evaluate(element => {
                const rect = element.getBoundingClientRect();
                const stage = document.querySelector("[data-atlas-museum-stage]")!.getBoundingClientRect();
                return Math.abs(rect.left + rect.width / 2 - stage.left - stage.width / 2);
            })).toBeLessThanOrEqual(10);
            await artwork.click();
        }
        await expect(overlay).toBeVisible();
        await expect(overlay.locator("img")).toHaveAttribute("src", legacy[0].image_url);
        const box = await overlay.boundingBox();
        if (!box) throw new Error("Viewer is missing");
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 200, { steps: 8 });
        await page.mouse.up();
        await expect(overlay).toHaveCount(0);
        await expect(artwork).toBeVisible();
    });
}

test("horizontal coverflow still centers artwork and collection changes reset the stage", async ({ page }) => {
    await mockArchive(page);
    await page.goto("/museum");
    await page.getByRole("button", { name: "Tablas", exact: true }).click();
    await expect(cards(page)).toHaveCount(3);
    const stage = page.locator("[data-atlas-museum-stage]");
    const lastCard = card(page, "table-3");
    // Dispatch the click without Playwright scrolling the card into view first.
    await lastCard.dispatchEvent("click");
    await expect.poll(() => stage.evaluate(element => element.scrollLeft)).toBeGreaterThan(100);
    await expect.poll(() => lastCard.evaluate(element => {
        const rect = element.getBoundingClientRect();
        const stageRect = document.querySelector("[data-atlas-museum-stage]")!.getBoundingClientRect();
        return Math.abs(rect.left + rect.width / 2 - stageRect.left - stageRect.width / 2);
    })).toBeLessThanOrEqual(10);
    await lastCard.click();
    const overlay = page.locator("[data-atlas-museum-artwork-overlay]");
    await expect(overlay).toBeVisible();
    await overlay.click();
    await expect(overlay).toHaveCount(0);
    await page.getByRole("button", { name: "Cartas Nuevas", exact: true }).click();
    await expect(cards(page)).toHaveCount(1);
    await expect(card(page, "new")).toBeVisible();
    await page.getByRole("button", { name: "Tablas", exact: true }).click();
    await expect(card(page, "archived-table")).toBeVisible();
    // A different collection must not retain the previous table's selection.
    await expect(overlay).toHaveCount(0);
});

test("AdminMuseum offers the four canonical categories and legacy upload values", async ({ page }) => {
    await mockArchive(page);
    await page.addInitScript(() => localStorage.setItem("token", "test-token"));
    await page.goto("/admin/museum");
    const selector = page.getByRole("combobox", { name: "Colección histórica" });
    for (const value of ["tap_list", "carta_vieja", "carta_nueva", "etiquetas",
        "fichas/antiguas", "fichas/actuales", "tap", "botellas"]) {
        await selector.selectOption(value);
        await expect(selector).toHaveValue(value);
    }
});
