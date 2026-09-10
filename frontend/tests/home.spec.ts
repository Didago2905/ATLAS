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
    await page.getByRole("button", { name: /Explorar modo museo/ }).click();
    await expect(page).toHaveURL(/\/museum$/);
});

test("sort exposes canonical values, orders cards, and persists tapFilter", async ({ page }) => {
    await openHome(page);
    const sort = page.locator("select");

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
