import { test, expect, type Page } from "@playwright/test";

const beers = [
    { id: 101, name: "Legacy First", brewery: "Tiburon", style: "IPA", color: "#f5a623", abv: 5, ibu: 30, description: "First beer.", origin: "Test", image_url: "/images/beer-art-101.png", beercard_background_url: null, prices: { pint: 80 }, is_available: true, is_featured: false, tap_position: 1, featured_updated_at: null },
    { id: 102, name: "Legacy Middle", brewery: "Tiburon", style: "Lager", color: "#f8d568", abv: 4.5, ibu: 20, description: "Middle beer.", origin: "Test", image_url: "/images/beer-art-102.png", beercard_background_url: null, prices: { pint: 75 }, is_available: true, is_featured: false, tap_position: 2, featured_updated_at: null },
    { id: 103, name: "Legacy Last", brewery: "Tiburon", style: "Stout", color: "#654321", abv: 6, ibu: 40, description: "Last beer.", origin: "Test", image_url: "/images/beer-art-103.png", beercard_background_url: null, prices: { pint: 85 }, is_available: true, is_featured: false, tap_position: 3, featured_updated_at: null },
];

type Point = { x: number; y: number };

async function openFirstBeer(page: Page) {
    await page.route("**/api/public/tap", (route) => route.fulfill({ json: beers }));
    await page.route("**/api/audit/**", (route) => route.fulfill({ status: 204 }));
    await page.goto("/");
    await expect(page.locator("body")).toHaveAttribute("data-atlas-ready", "true");
    await page.locator('[data-atlas-tap-card="101"]').click();
    await expect(page).toHaveURL(/\/beer\/101$/);
    await expect(page.locator('[data-atlas-card="101"]')).toBeVisible();
}

async function swipe(page: Page, selector: string, start: Point, end: Point) {
    await page.locator(selector).evaluate((target, points) => {
        const makeTouch = (point: Point) => ({
            identifier: 1,
            target,
            clientX: point.x,
            clientY: point.y,
            pageX: point.x,
            pageY: point.y,
            screenX: point.x,
            screenY: point.y,
        });
        const dispatch = (type: string, touches: ReturnType<typeof makeTouch>[], changedTouches: ReturnType<typeof makeTouch>[]) => {
            const event = new Event(type, { bubbles: true, cancelable: true });
            Object.defineProperty(event, "touches", { value: touches });
            Object.defineProperty(event, "changedTouches", { value: changedTouches });
            target.dispatchEvent(event);
        };
        const startTouch = makeTouch(points.start);
        const endTouch = makeTouch(points.end);
        dispatch("touchstart", [startTouch], [startTouch]);
        dispatch("touchmove", [endTouch], [endTouch]);
        dispatch("touchend", [], [endTouch]);
    }, { start, end });
}

const swipeLeft = (page: Page, selector = ".beer-card") => swipe(page, selector, { x: 220, y: 300 }, { x: 120, y: 300 });
const swipeRight = (page: Page, selector = ".beer-card") => swipe(page, selector, { x: 120, y: 300 }, { x: 220, y: 300 });
const swipeUp = (page: Page, selector = ".beer-card") => swipe(page, selector, { x: 180, y: 360 }, { x: 180, y: 250 });
const swipeDown = (page: Page, selector: string) => swipe(page, selector, { x: 180, y: 250 }, { x: 180, y: 360 });

test.beforeEach(async ({ page }) => {
    await openFirstBeer(page);
});

test("ATLAS BeerDetail Screenshot", async ({ page, browserName }) => {
    await page.screenshot({
        path: `../devtools/testing/playwright/screenshots/beerdetail-${browserName}.png`,
        fullPage: true,
    });
});

test("legacy horizontal swipe left navigates to the next beer", async ({ page }) => {
    await swipeLeft(page);
    await expect(page).toHaveURL(/\/beer\/102$/);
    await expect(page.locator('[data-atlas-card="102"]')).toBeVisible();
});

test("legacy horizontal swipe right navigates to the previous beer", async ({ page }) => {
    await swipeLeft(page);
    await expect(page).toHaveURL(/\/beer\/102$/);
    await swipeRight(page);
    await expect(page).toHaveURL(/\/beer\/101$/);
    await expect(page.locator('[data-atlas-card="101"]')).toBeVisible();
});

test("legacy vertical swipes switch from Info to FullArt and back", async ({ page }) => {
    const art = page.locator('img[src="/images/beer-art-101.png"]');
    await expect(art).toHaveCount(0);
    await swipeUp(page);
    await expect(art).toBeVisible();
    await swipeDown(page, 'img[src="/images/beer-art-101.png"]');
    await expect(art).toHaveCount(0);
    await expect(page.locator('[data-atlas-card="101"]')).toBeVisible();
});

test("legacy navigation stops at the first and last beer", async ({ page }) => {
    await swipeRight(page);
    await expect(page).toHaveURL(/\/beer\/101$/);
    await swipeLeft(page);
    await expect(page).toHaveURL(/\/beer\/102$/);
    await swipeLeft(page);
    await expect(page).toHaveURL(/\/beer\/103$/);
    await swipeLeft(page);
    await page.waitForTimeout(50);
    await expect(page).toHaveURL(/\/beer\/103$/);
    await expect(page.locator('[data-atlas-card="103"]')).toBeVisible();
});

test("legacy beer-to-beer navigation replaces the current history entry", async ({ page }) => {
    await swipeLeft(page);
    await expect(page).toHaveURL(/\/beer\/102$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/$/);
});
