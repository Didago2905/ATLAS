import { test, expect } from "@playwright/test";

test("ATLAS Home Screenshot", async ({ page, browserName }) => {

    await page.goto("/");

    await expect(page.locator("body"))
        .toHaveAttribute(
            "data-atlas-ready",
            "true"
        );

    await page.screenshot({
        path: `../devtools/testing/playwright/screenshots/home-${browserName}.png`,
        fullPage: true,
    });

});