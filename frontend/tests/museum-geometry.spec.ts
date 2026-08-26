import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("ATLAS Museum layout reachability", async ({ page }) => {
    test.setTimeout(90_000);

    await page.goto("http://bs-local.com:3000/museum");

    const stage = page.locator("[data-atlas-museum-stage]");
    const track = page.locator("[data-atlas-museum-track]");
    const selector = page.locator("[data-atlas-museum-selector]");

    const readGeometry = async () => track.evaluate(trackElement => {
        const stageElement = trackElement.parentElement;

        if (!stageElement) {
            throw new Error("Museum stage is unavailable for geometry capture");
        }

        const cards = Array.from(trackElement.children).filter(
            child => child.querySelector("img")
        );

        if (cards.length === 0) {
            throw new Error("Museum track contains no BeerCover layout slots");
        }

        const maxScrollLeft =
            stageElement.scrollWidth - stageElement.clientWidth;
        const cardGeometry = (card, index) => {
            const desiredScrollLeft =
                card.offsetLeft -
                stageElement.offsetWidth / 2 +
                card.offsetWidth / 2;

            return {
                index,
                offsetLeft: card.offsetLeft,
                offsetWidth: card.offsetWidth,
                desiredScrollLeft,
                reachabilityDelta: desiredScrollLeft - maxScrollLeft,
            };
        };
        const trackRect = trackElement.getBoundingClientRect();

        return {
            cardCount: cards.length,
            stage: {
                offsetWidth: stageElement.offsetWidth,
                clientWidth: stageElement.clientWidth,
                scrollWidth: stageElement.scrollWidth,
                maxScrollLeft,
                scrollLeft: stageElement.scrollLeft,
            },
            track: {
                offsetWidth: trackElement.offsetWidth,
                clientWidth: trackElement.clientWidth,
                scrollWidth: trackElement.scrollWidth,
                boundingRectWidth: trackRect.width,
            },
            firstCard: cardGeometry(cards[0], 0),
            lastCard: cardGeometry(cards[cards.length - 1], cards.length - 1),
        };
    });

    const assertReachable = (collection) => {
        for (const card of [collection.firstCard, collection.lastCard]) {
            expect(card.desiredScrollLeft).toBeGreaterThanOrEqual(0);
            expect(card.desiredScrollLeft).toBeLessThanOrEqual(
                collection.stage.maxScrollLeft
            );
        }
    };

    await expect(stage).toBeVisible();
    await expect(track).toBeVisible();
    await expect(selector).toBeVisible();
    await expect.poll(async () => (await readGeometry()).cardCount)
        .toBeGreaterThan(0);

    const fichas = await readGeometry();

    await selector.getByRole("button").nth(1).click();
    await expect.poll(async () => (await readGeometry()).cardCount, {
        timeout: 5_000,
    }).not.toBe(fichas.cardCount);

    const tap = await readGeometry();
    const artifact = { fichas, tap };
    const resultsDirectory = path.resolve("tests", "results");

    fs.mkdirSync(resultsDirectory, { recursive: true });
    fs.writeFileSync(
        path.join(resultsDirectory, "museum-track-geometry.json"),
        JSON.stringify(artifact, null, 2),
        "utf8"
    );

    assertReachable(fichas);
    assertReachable(tap);
});
