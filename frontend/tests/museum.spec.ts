import { test, expect } from "@playwright/test";

test("ATLAS Museum Screenshot", async ({ page, browserName }) => {

    await page.goto("/museum");

    await expect(page.locator("body"))
        .toHaveAttribute(
            "data-atlas-ready",
            "true"
        );

    await page.screenshot({
        path: `../devtools/testing/playwright/screenshots/museum-${browserName}.png`,
        fullPage: true,
    });

});