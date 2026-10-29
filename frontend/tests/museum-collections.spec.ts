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

test.describe("Museum search and filters", () => {
    test.use({ hasTouch: true });
    const field = (value: string, confidence = "confirmed") => ({ value, confidence, evidence: "secreto_en_evidencia" });
    const product = (name: string, style: string, brewery: string, origin = "Xalapa, Veracruz", confidence = "confirmed") => ({
        beer_name: field(name), beer_style: field(style), brewery: field(brewery, confidence), brewery_origin: field(origin, confidence),
    });
    const piece = (id: string, name: string, products: unknown, extra = {}) => ({
        id, name, category: "carta_vieja", image_url: image,
        semantic_products: typeof products === "string" ? products : JSON.stringify(products), ...extra,
    });
    const fixtures = [
        piece("z", "Zeta", [product("Zeta", "IPA", "Alpha")]),
        piece("legacy", "Águila", undefined, { category: undefined, type: "fichas/antiguas", style: "Porter" }),
        piece("multi", "Múltiple", [product("Primera", "IPA", "Alpha"), product("Segunda", "Stout", "Beta", "Mérida, Yucatán")]),
        piece("broken", "Roto", "{", { notes: "solo_en_notas" }),
        piece("missing", "Sin ficha", undefined),
        piece("probable", "Provisional", [product("Provisional", "Pils", "Fantasma", "Origen provisional", "probable")]),
        piece("tie-a", "Águila", [product("Águila", "Blonde Ale", "Gamma")]),
        piece("tie-b", "águila", [product("águila", "Blonde Ale", "Gamma")]),
        piece("untitled", "", []),
        piece("new", "Águila nueva", [product("Águila nueva", "NEIPA", "Nueva")], { category: "carta_nueva" }),
        piece("personal", "Navidad", [], { category: "etiquetas" }),
        piece("table", "Tabla", [], { category: "tap_list" }),
    ];
    const ids = (page: Page) => cards(page).evaluateAll(nodes => nodes.map(node => node.getAttribute("data-atlas-museum-card-id")));
    const panel = (page: Page) => page.getByRole("region", { name: "Explorar Museo" });
    const trigger = (page: Page) => page.getByRole("button", { name: "Buscar en el Museo", exact: true });
    const open = async (page: Page) => {
        await trigger(page).click();
        await expect(panel(page)).toBeVisible();
    };
    const setup = async (page: Page) => {
        await mockArchive(page, fixtures);
        await page.goto("/museum");
        await expect(cards(page)).toHaveCount(9);
    };
    const centered = async (page: Page, id: string) => {
        await expect.poll(() => card(page, id).evaluate(node => {
            const stage = document.querySelector("[data-atlas-museum-stage]")!;
            return Math.abs((node as HTMLElement).offsetLeft + (node as HTMLElement).offsetWidth / 2 - stage.scrollLeft - stage.clientWidth / 2);
        })).toBeLessThanOrEqual(2);
    };

    test("searches only usable values, handles legacy/malformed data and matches one semantic product", async ({ page }) => {
        await page.addInitScript(() => {
            (window as any).semanticParses = 0;
            const parse = JSON.parse;
            JSON.parse = (value, ...args) => {
                if (typeof value === "string" && value.includes('"beer_name"')) (window as any).semanticParses++;
                return parse(value, ...args);
            };
        });
        await setup(page);
        const parses = await page.evaluate(() => (window as any).semanticParses);
        expect(parses).toBeGreaterThan(0);
        await open(page);
        const style = panel(page).getByRole("combobox", { name: "Estilo de cerveza" });
        const brewery = panel(page).getByRole("combobox", { name: "Cervecería", exact: true });
        const search = page.getByRole("searchbox", { name: "Buscar obras" });
        await expect(brewery.locator("option")).toHaveText(["Todas las cervecerías", "Alpha", "Beta", "Gamma"]);
        await style.selectOption("ipa");
        await brewery.selectOption("beta");
        await expect(cards(page)).toHaveCount(0);
        await expect(page.getByText("No hay obras que coincidan con los filtros.", { exact: true })).toBeVisible();
        await style.selectOption("stout");
        await expect.poll(() => ids(page)).toEqual(["multi"]);
        await panel(page).getByRole("button", { name: "Limpiar filtros" }).click();
        await search.fill("MERIDA");
        await expect.poll(() => ids(page)).toEqual(["multi"]);
        await search.fill("aguila");
        await expect.poll(() => ids(page)).toEqual(["legacy", "tie-a", "tie-b"]);
        await search.fill("Porter");
        await expect.poll(() => ids(page)).toEqual(["legacy"]);
        await search.fill("Beta");
        await expect.poll(() => ids(page)).toEqual(["multi"]);
        for (const term of ["secreto_en_evidencia", "solo_en_notas", "Fantasma", "Origen provisional"]) {
            await search.fill(term);
            await expect(cards(page)).toHaveCount(0);
        }
        await search.fill("");
        await expect(cards(page)).toHaveCount(9);
        await expect(panel(page).getByRole("status")).toHaveText("9 de 9 obras");
        expect(await page.evaluate(() => (window as any).semanticParses)).toBe(parses);
    });

    test("stable ordering preserves the centered ID; collection changes keep query/order and reset facets", async ({ page }) => {
        await setup(page);
        await card(page, "multi").dispatchEvent("click");
        await centered(page, "multi");
        await open(page);
        const order = page.getByRole("combobox", { name: "Orden del Museo" });
        await order.selectOption("az");
        await expect.poll(() => ids(page)).toEqual(["legacy", "tie-a", "tie-b", "multi", "probable", "broken", "missing", "z", "untitled"]);
        await centered(page, "multi");
        await order.selectOption("za");
        await expect.poll(() => ids(page)).toEqual(["z", "missing", "broken", "probable", "multi", "legacy", "tie-a", "tie-b", "untitled"]);
        await centered(page, "multi");
        await page.getByRole("searchbox").fill("Zeta");
        await expect.poll(() => ids(page)).toEqual(["z"]);
        await centered(page, "z");
        await page.getByRole("searchbox").fill("aguila");
        await page.getByRole("combobox", { name: "Estilo de cerveza" }).selectOption("blonde ale");
        await page.getByRole("combobox", { name: "Cervecería", exact: true }).selectOption("gamma");
        await page.getByRole("button", { name: "Cartas Nuevas", exact: true }).click();
        await expect.poll(() => ids(page)).toEqual(["new"]);
        await open(page);
        await expect(page.getByRole("searchbox")).toHaveValue("aguila");
        await expect(order).toHaveValue("za");
        await expect(page.getByRole("combobox", { name: "Estilo de cerveza" })).toHaveValue("");
        await expect(page.getByRole("combobox", { name: "Cervecería", exact: true })).toHaveValue("");
        await page.getByRole("button", { name: "Etiquetas", exact: true }).click();
        await expect(cards(page)).toHaveCount(0);
        await page.getByRole("button", { name: "Limpiar filtros", exact: true }).click();
        await expect.poll(() => ids(page)).toEqual(["personal"]);
    });

    test("panel opening does not focus input; shared visibility, Escape, outside click and viewer remain functional", async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 720 });
        await setup(page);
        await open(page);
        const input = page.getByRole("searchbox");
        await expect(input).not.toBeFocused();
        await expect(trigger(page)).toHaveAttribute("aria-expanded", "true");
        await page.evaluate(() => window.dispatchEvent(new Event("touchmove")));
        for (const selector of ["[data-atlas-museum-back]", "[data-atlas-museum-search]", "[data-atlas-museum-selector]"]) {
            await expect(page.locator(selector)).toHaveCSS("opacity", "1");
        }
        await input.focus();
        await page.keyboard.press("Escape");
        await expect(panel(page)).toHaveCount(0);
        await expect(trigger(page)).toBeFocused();
        await open(page);
        await page.mouse.click(700, 50);
        await expect(panel(page)).toHaveCount(0);
        await open(page);
        await input.fill("Múltiple");
        await centered(page, "multi");
        await card(page, "multi").click();
        await expect(panel(page)).toHaveCount(0);
        await expect(page.locator("[data-atlas-museum-artwork-overlay]")).toBeVisible();
        await trigger(page).click();
        await expect(page.locator("[data-atlas-museum-artwork-overlay]")).toHaveCount(0);
        await expect(panel(page)).toBeVisible();
        await expect(input).not.toBeFocused();
        await page.keyboard.press("Escape");
        await page.evaluate(() => window.dispatchEvent(new Event("touchmove")));
        await expect.poll(() => trigger(page).evaluate(e => e.style.opacity)).toBe("0");
        await expect.poll(() => trigger(page).evaluate(e => e.style.opacity)).toBe("1");
    });

    for (const viewport of [{ width: 320, height: 568 }, { width: 390, height: 844 }, { width: 568, height: 320 }, { width: 844, height: 390 }]) {
        test(`navigation controls and panel fit at ${viewport.width}x${viewport.height}`, async ({ page }) => {
            await page.setViewportSize(viewport);
            await setup(page);
            const selectors = ["[data-atlas-museum-back]", "[data-atlas-museum-search]", "[data-atlas-museum-selector]"];
            const boxes = await Promise.all(selectors.map(s => page.locator(s).boundingBox()));
            for (const b of boxes) {
                expect(b).toBeTruthy();
                expect(b!.x).toBeGreaterThanOrEqual(0); expect(b!.y).toBeGreaterThanOrEqual(0);
                expect(b!.x + b!.width).toBeLessThanOrEqual(viewport.width);
                expect(b!.y + b!.height).toBeLessThanOrEqual(viewport.height);
            }
            for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
                const a = boxes[i]!, b = boxes[j]!;
                expect(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y).toBe(true);
            }
            expect(boxes[1]!.width).toBe(44); expect(boxes[1]!.height).toBe(44);
            await trigger(page).tap();
            await expect(page.getByRole("searchbox")).not.toBeFocused();
            const box = await panel(page).boundingBox();
            expect(box!.y).toBeGreaterThanOrEqual(Math.max(boxes[0]!.y + 44, boxes[1]!.y + 44));
            expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
            expect(box!.x).toBeGreaterThanOrEqual(0); expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);
            await expect(panel(page)).toHaveCSS("overflow-y", "auto");
            await page.getByRole("button", { name: "Cerrar búsqueda" }).click();
            await expect(trigger(page)).toBeFocused();
            await page.getByRole("button", { name: "Volver", exact: true }).click();
            await expect(page).toHaveURL("http://127.0.0.1:5173/");
            await page.goBack();
            // Direct-entry fallback replaces /museum, so Back cannot loop into it.
            expect(page.url()).not.toMatch(/\/museum$/);
        });
    }

    test("keyboard-sized height changes resize only the panel, not artwork geometry or orientation", async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 844 });
        await setup(page);
        await centered(page, "z");
        const before = await cards(page).evaluateAll(nodes => nodes.map(e => [e.getAttribute("data-atlas-museum-card-id"), (e as HTMLElement).style.width, (e as HTMLElement).style.height]));
        await open(page);
        await page.getByRole("searchbox").focus();
        await page.setViewportSize({ width: 390, height: 300 });
        await expect(page.locator("[data-atlas-museum-selector]")).toHaveCSS("flex-direction", "row");
        expect(await cards(page).evaluateAll(nodes => nodes.map(e => [e.getAttribute("data-atlas-museum-card-id"), (e as HTMLElement).style.width, (e as HTMLElement).style.height]))).toEqual(before);
        await centered(page, "z");
        await expect.poll(async () => {
            const box = await panel(page).boundingBox();
            return box!.y + box!.height;
        }).toBeLessThanOrEqual(300);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.getByRole("searchbox").blur();
        await page.setViewportSize({ width: 844, height: 390 });
        await expect(page.locator("[data-atlas-museum-selector]")).toHaveCSS("flex-direction", "column");
        await centered(page, "z");
    });
});
