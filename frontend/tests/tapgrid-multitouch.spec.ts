import { test, expect, type Page } from "@playwright/test";

const beer = {
    id: 1,
    name: "Gesture Test Beer",
    style: "Test Style",
    abv: 5,
    tap_position: 1,
    is_featured: false,
    image_url: "",
};

async function openTapGrid(page: Page) {
    await page.route("**/api/public/tap", (route) =>
        route.fulfill({ json: [beer] })
    );
    await page.route("**/api/audit/**", (route) =>
        route.fulfill({ status: 204 })
    );
    await page.goto("/");
    await expect(page.locator("[data-atlas-tap-card]"))
        .toHaveCount(1);
}

async function dispatchTouch(page: Page, type: string, touchCount: number) {
    await page.evaluate(({ eventType, count }) => {
        const event = new Event(eventType, {
            bubbles: true,
            cancelable: true,
        });
        Object.defineProperty(event, "touches", {
            value: Array.from({ length: count }, (_, identifier) => ({ identifier })),
        });
        window.dispatchEvent(event);
    }, { eventType: type, count: touchCount });
}

test("a normal card click still opens BeerDetail", async ({ page }) => {
    await openTapGrid(page);

    await page.locator("[data-atlas-tap-card]").click();

    await expect(page).toHaveURL(/\/beer\/1$/);
});

test("multitouch evidence suppresses a residual card click", async ({ page }) => {
    await openTapGrid(page);

    await dispatchTouch(page, "touchstart", 1);
    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await page.locator("[data-atlas-tap-card]").click();
    await page.waitForTimeout(300);

    await expect(page).toHaveURL(/\/$/);
});

test("recognized two-finger double tap toggles mode without navigation", async ({ page }) => {
    await openTapGrid(page);

    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await expect.poll(() => page.evaluate(() =>
        localStorage.getItem("tap_grid_mode")
    )).toBe("gallery");

    await page.locator("[data-atlas-tap-card]").click();
    await page.waitForTimeout(300);

    await expect(page).toHaveURL(/\/$/);
});

test("touchcancel clears the guard for the next normal activation", async ({ page }) => {
    await openTapGrid(page);

    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchcancel", 0);
    await page.locator("[data-atlas-tap-card]").click();

    await expect(page).toHaveURL(/\/beer\/1$/);
});

test("completed multitouch guard expires before a later normal activation", async ({ page }) => {
    await openTapGrid(page);

    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await page.waitForTimeout(375);
    await page.locator("[data-atlas-tap-card]").click();

    await expect(page).toHaveURL(/\/beer\/1$/);
});
