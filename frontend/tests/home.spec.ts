import { test, expect, type Page } from "@playwright/test";

const beers = [
    { id: 1, name: "Zulu", style: "Stout", abv: 4, tap_position: 3, is_featured: false, image_url: "" },
    { id: 2, name: "Alpha", style: "Lager", abv: 8, tap_position: 2, is_featured: false, image_url: "" },
    { id: 3, name: "Bravo", style: "IPA", abv: 6, tap_position: 1, is_featured: true, featured_updated_at: 1, image_url: "" },
];

async function routeHome(page: Page, items = beers) {
    await page.route("**/api/public/tap", route => route.fulfill({ json: items }));
    await page.route("**/api/public/museum", route => route.fulfill({ json: [] }));
    await page.route("**/api/audit/**", route => route.fulfill({ status: 204 }));
}

async function openHome(page: Page, items = beers) {
    await routeHome(page, items);
    await page.goto("/");
    await expect(page.locator("body")).toHaveAttribute("data-atlas-ready", "true");
}

const grid = (page: Page) => page.locator('div[style*="display: grid"]');

async function cardIds(page: Page) {
    return page.locator("[data-atlas-tap-card]").evaluateAll(cards =>
        cards.map(card => card.getAttribute("data-atlas-tap-card"))
    );
}

test("Home navigates to Museum", async ({ page }) => {
    await openHome(page);
    await expect(page.getByText("Explorar modo museo", { exact: false })).toHaveCount(0);
    await page.getByRole("button", { name: "Museo", exact: true }).click();
    await expect(page).toHaveURL(/\/museum$/);
});

test("Home presents Tiburón Tap List branding and TapGrid", async ({ page }) => {
    await openHome(page);
    await expect(page.getByRole("heading", { name: "TIBURÓN TAP LIST" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "ATLAS", exact: true })).toHaveCount(0);
    await expect(page.getByText("Taproom Manager", { exact: true })).toHaveCount(0);
    await expect(grid(page)).toBeVisible();
});

test("sort exposes canonical values, orders cards, and persists tapFilter", async ({ page }) => {
    await openHome(page);
    const sort = page.getByRole("combobox", { name: "Orden" });
    await expect(sort.locator("option")).toHaveText(["Tap", "Alcohol", "Nombre", "Estilo"]);

    await expect.poll(() => sort.locator("option").evaluateAll(options =>
        options.map(option => (option as HTMLOptionElement).value)
    )).toEqual(["tap", "abv", "name", "style"]);
    await expect.poll(() => cardIds(page)).toEqual(["3", "2", "1"]);

    const expectations = {
        abv: ["2", "3", "1"],
        name: ["2", "3", "1"],
        style: ["3", "2", "1"],
        tap: ["3", "2", "1"],
    };
    for (const [value, expected] of Object.entries(expectations)) {
        await sort.selectOption(value);
        await expect.poll(() => cardIds(page)).toEqual(expected);
        await expect.poll(() => page.evaluate(() => localStorage.getItem("tapFilter")))
            .toBe(JSON.stringify({ sort: value }));
    }

    await sort.selectOption("abv");
    await page.reload();
    await expect(sort).toHaveValue("abv");
    await expect.poll(() => cardIds(page)).toEqual(expectations.abv);
});

test("TapGrid caps and fills exactly 16 slots with a 3/4 aspect ratio", async ({ page }) => {
    const manyBeers = Array.from({ length: 18 }, (_, index) => ({
        ...beers[index % beers.length], id: index + 1,
        name: `Beer ${String(index + 1).padStart(2, "0")}`,
        is_featured: false, tap_position: index + 1,
    }));
    await openHome(page, manyBeers);

    await expect(page.locator("[data-atlas-tap-card]")).toHaveCount(16);
    await expect(grid(page).locator(":scope > div")).toHaveCount(16);

    await page.unroute("**/api/public/tap");
    await page.route("**/api/public/tap", route => route.fulfill({ json: beers.slice(0, 2) }));
    await page.reload();
    await expect(page.locator("[data-atlas-tap-card]")).toHaveCount(2);
    await expect(grid(page).locator(":scope > div")).toHaveCount(16);

    const ratios = await grid(page).locator(":scope > div").evaluateAll(elements =>
        elements.map(element => {
            const rect = element.getBoundingClientRect();
            return rect.width / rect.height;
        })
    );
    for (const ratio of ratios) expect(ratio).toBeCloseTo(0.75, 2);
});

test("loading skeletons retain 16 slots with a 3/4 aspect ratio", async ({ page }) => {
    await page.route("**/api/public/tap", async route => {
        await new Promise(resolve => setTimeout(resolve, 1_000));
        await route.fulfill({ json: beers });
    });
    await page.goto("/");

    await expect(grid(page).locator(":scope > div")).toHaveCount(16);
    const ratios = await grid(page).locator(":scope > div").evaluateAll(elements =>
        elements.map(element => {
            const rect = element.getBoundingClientRect();
            return rect.width / rect.height;
        })
    );
    for (const ratio of ratios) expect(ratio).toBeCloseTo(0.75, 2);
});

test.describe("TapGrid protected geometry", () => {
    for (const { name, width, height, mode, columns } of [
        { name: "mobile Focus", width: 390, height: 844, mode: "focus", columns: 2 },
        { name: "mobile Gallery", width: 390, height: 844, mode: "gallery", columns: 3 },
        { name: "tablet", width: 700, height: 900, mode: "focus", columns: 3 },
        { name: "desktop", width: 1000, height: 800, mode: "focus", columns: 4 },
    ]) {
        test(`${name} keeps wrapper padding, gap, columns, and internal mode`, async ({ page }) => {
            await page.setViewportSize({ width, height });
            await page.addInitScript(selectedMode => {
                localStorage.setItem("tap_grid_mode", selectedMode);
            }, mode);
            await openHome(page);

            const geometry = await grid(page).evaluate(element => {
                const gridStyle = getComputedStyle(element);
                const wrapperStyle = getComputedStyle(element.parentElement!);
                return {
                    columns: gridStyle.gridTemplateColumns.split(" ").length,
                    gap: gridStyle.gap,
                    padding: wrapperStyle.padding,
                };
            });
            expect(geometry).toEqual({ columns, gap: "12px", padding: "20px" });
            await expect.poll(() => page.evaluate(() => localStorage.getItem("tap_grid_mode")))
                .toBe(mode);
        });
    }
});

test("featured marker does not intercept normal BeerDetail activation", async ({ page }) => {
    await openHome(page);
    const featured = page.locator('[data-atlas-tap-card="3"]');
    const marker = featured.getByText("⭐");

    await expect(marker).toBeVisible();
    await expect(marker).toHaveCSS("pointer-events", "none");
    await featured.click();

    await expect(page).toHaveURL(/\/beer\/3$/);
});


test("Tap List settings open and dismiss accessibly", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => localStorage.setItem("atlas_museum_background", "burgundy"));
    await openHome(page);
    const trigger = page.getByRole("button", { name: "Configuración de Tap List" });
    const panel = page.getByRole("region", { name: "Apariencia" });
    const layout = page.locator(".tap-list-layout");
    await expect(layout).toHaveAttribute("data-taplist-background", "black");
    await trigger.click();
    await expect(panel).toBeVisible();
    await trigger.click();
    await expect(panel).toHaveCount(0);
    await trigger.click();
    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await trigger.click();
    await page.getByRole("heading", { name: "TIBURÓN TAP LIST" }).click();
    await expect(panel).toHaveCount(0);
});

for (const [id, label, center] of [
        ["black", "Negro", ""],
        ["petrol", "Petróleo", "52, 70, 77"],
        ["burgundy", "Borgoña", "89, 48, 57"],
        ["gallery-light", "Galería clara", "240, 237, 230"],
    ]) {
    test(`Tap List applies ${id}`, async ({ page }) => {
        await openHome(page);
        const trigger = page.getByRole("button", { name: "Configuración de Tap List" });
        const panel = page.getByRole("region", { name: "Apariencia" });
        const layout = page.locator(".tap-list-layout");
        await trigger.click();
        await panel.getByRole("button", { name: label, exact: true }).click();
        await expect(panel).toHaveCount(0);
        await expect(layout).toHaveAttribute("data-taplist-background", id);
        if (id === "black") await expect(layout).toHaveCSS("background-color", "rgb(0, 0, 0)");
        else expect(await layout.evaluate(el => getComputedStyle(el).backgroundImage)).toContain(center);
        expect(await page.evaluate(() => localStorage.getItem("atlas_taplist_background"))).toBe(id);
    });
}

test("Tap List selection survives reload independently from Museum", async ({ page }) => {
    await openHome(page);
    await page.evaluate(() => localStorage.setItem("atlas_museum_background", "burgundy"));
    const trigger = page.getByRole("button", { name: "Configuración de Tap List" });
    const panel = page.getByRole("region", { name: "Apariencia" });
    const layout = page.locator(".tap-list-layout");
    await trigger.click();
    await panel.getByRole("button", { name: "Galería clara" }).click();
    await page.reload();
    await expect(layout).toHaveAttribute("data-taplist-background", "gallery-light");
    await expect(page.locator(".tap-list-header")).toHaveCSS("color", "rgb(34, 34, 34)");
    await trigger.click();
    await expect(panel.getByRole("button", { name: "Galería clara" })).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Museo", exact: true }).click();
    await expect(page).toHaveURL(/\/museum$/);
    expect(await page.evaluate(() => localStorage.getItem("atlas_museum_background"))).toBe("burgundy");

    expect(await page.evaluate(() => localStorage.getItem("atlas_taplist_background"))).toBe("gallery-light");
});

test("Tap List rejects corrupt background without reading Museum preference", async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("atlas_taplist_background", "{broken");
        localStorage.setItem("atlas_museum_background", "petrol");
    });
    await openHome(page);
    await expect(page.locator(".tap-list-layout")).toHaveAttribute("data-taplist-background", "black");
    await expect(page.locator(".tap-list-layout")).toHaveCSS("background-color", "rgb(0, 0, 0)");
});
