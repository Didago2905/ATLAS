import { test, expect } from "@playwright/test";

test("ATLAS BeerDetail Screenshot", async ({ page, browserName }) => {

    // Abrir Home
    await page.goto("/");

    // Esperar que ATLAS termine de cargar
    await expect(page.locator("body"))
        .toHaveAttribute(
            "data-atlas-ready",
            "true"
        );

    // Abrir la primera cerveza del Tap
    await page
        .locator("[data-atlas-tap-card]")
        .first()
        .click();

    // Verificar navegación
    await expect(page).toHaveURL(/\/beer\/\d+/);

    // Esperar que BeerDetail termine de renderizar
    await expect(page.locator("body"))
        .toHaveAttribute(
            "data-atlas-ready",
            "true"
        );

    // Captura
    await page.screenshot({
        path: `../devtools/testing/playwright/screenshots/beerdetail-${browserName}.png`,
        fullPage: true,
    });

});