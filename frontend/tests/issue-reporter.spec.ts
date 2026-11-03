import { test, expect, type Page } from "@playwright/test";

async function openReporter(page: Page) {
    await page.addInitScript(() => localStorage.setItem("atlas_tutorial_outcome_v1", "completed"));
    await page.route("**/api/public/tap", route => route.fulfill({ json: [] }));
    await page.goto("/?privateQuery=do-not-collect#private-hash");
    await page.getByRole("button", { name: "Configuración de Tap List" }).click();
    await page.getByRole("button", { name: "Reportar un problema", exact: true }).click();
    return page.getByRole("dialog", { name: "Reportar un problema" });
}

test("reporter validates user information, contains focus, and preserves its memory draft", async ({ page }) => {
    const posts: string[] = [];
    page.on("request", request => { if (request.method() === "POST") posts.push(request.url()); });
    const dialog = await openReporter(page);
    await expect(dialog).toBeVisible();
    await expect(page.locator(".tap-list-settings__panel")).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Cerrar reporte" })).toBeFocused();
    await expect(dialog.getByRole("textbox")).toHaveCount(0);
    await dialog.getByLabel("Autorizo incluir datos técnicos", { exact: false }).check();
    await expect(dialog.getByRole("status")).toContainText("Elige al menos una categoría");
    await dialog.getByLabel("Tap List", { exact: true }).check();
    await dialog.getByLabel("Museo", { exact: true }).check();
    const description = dialog.getByRole("textbox", { name: "¿Qué pasó?" });
    await description.fill("                   corto                 ");
    await expect(description).toHaveAttribute("aria-invalid", "true");
    await description.fill("🐟".repeat(10));
    await expect(description).toHaveAttribute("aria-invalid", "true");
    await description.fill("x".repeat(2001));
    await expect(description).toHaveAttribute("aria-invalid", "true");
    await description.fill("La lista no aparece al abrir la página.");
    await expect(dialog.getByRole("status")).toContainText("Listo para enviar");
    await expect(dialog.getByRole("button", { name: "Enviar reporte" })).toBeEnabled();
    await dialog.getByRole("button", { name: "Cerrar reporte" }).focus();
    await page.keyboard.press("Shift+Tab");
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("button", { name: "Cerrar reporte" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    const trigger = page.getByRole("button", { name: "Configuración de Tap List" });
    await expect(trigger).toBeFocused();
    await trigger.click();
    await expect(page.getByRole("button", { name: "Repetir tutorial" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Consejos", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Créditos", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Negro", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Reportar un problema", exact: true }).click();
    await expect(description).toHaveValue("La lista no aparece al abrir la página.");
    await dialog.getByLabel("Tap List", { exact: true }).uncheck();
    await dialog.getByLabel("Museo", { exact: true }).uncheck();
    await expect(description).toHaveCount(0);
    await expect(dialog.getByRole("status")).toContainText("Elige al menos una categoría");
    await dialog.getByLabel("Otro", { exact: true }).check();
    await expect(description).toHaveValue("La lista no aparece al abrir la página.");
    expect(await page.evaluate(() => Object.values(localStorage).join(" "))).not.toContain("La lista no aparece");
    expect(posts).toEqual([]);
});

test("diagnostics require consent and exclude query, hash, storage and form content", async ({ page }) => {
    await page.addInitScript(() => {
        Object.defineProperty(navigator, "connection", { configurable: true, value: undefined });
        Object.defineProperty(window, "visualViewport", { configurable: true, value: undefined });
        Object.defineProperty(screen, "orientation", { configurable: true, value: undefined });
        localStorage.setItem("token", "private-token-marker");
    });
    const dialog = await openReporter(page);
    await expect(dialog.locator("pre")).toHaveCount(0);
    await dialog.getByLabel("Otro", { exact: true }).check();
    await dialog.getByRole("textbox").fill("private-description-marker of sufficient length");
    const consent = dialog.getByLabel("Autorizo incluir datos técnicos", { exact: false });
    await page.evaluate(() => {
        (window as any).snapshotReads = 0;
        Object.defineProperty(navigator, "connection", { configurable: true, get() {
            (window as any).snapshotReads++;
            return undefined;
        } });
    });
    await expect(dialog.getByRole("button", { name: "Ver datos técnicos" })).toHaveCount(0);
    expect(await page.evaluate(() => (window as any).snapshotReads)).toBe(0);
    await consent.check();
    expect(await page.evaluate(() => (window as any).snapshotReads)).toBe(1);
    const disclosure = dialog.getByRole("button", { name: "Ver datos técnicos" });
    await expect(disclosure).toHaveAttribute("aria-expanded", "false");
    await expect(dialog.locator("pre")).not.toBeVisible();
    await disclosure.focus();
    await page.keyboard.press("Enter");
    await expect(dialog.getByRole("button", { name: "Ocultar datos técnicos" })).toHaveAttribute("aria-expanded", "true");
    await expect(dialog.locator("pre")).toBeVisible();
    const raw = await dialog.locator("pre").innerText();
    const snapshot = JSON.parse(raw);
    expect(snapshot.route).toBe("/");
    expect(snapshot.network).toBeNull();
    expect(snapshot.visualViewport).toBeNull();
    expect(snapshot.orientation).toBeNull();
    expect(snapshot.viewport.width).toBeGreaterThan(0);
    expect(Object.keys(snapshot).sort()).toEqual([
        "schemaVersion", "timestamp", "timezone", "utcOffsetMinutes", "route", "browser", "os",
        "viewport", "screen", "visualViewport", "devicePixelRatio", "orientation", "online", "network",
    ].sort());
    for (const secret of ["privateQuery", "private-hash", "private-token-marker", "private-description-marker"]) {
        expect(raw).not.toContain(secret);
    }
    await dialog.getByRole("button", { name: "Ocultar datos técnicos" }).click();
    await expect(consent).toBeChecked();
    await dialog.getByRole("button", { name: "Ver datos técnicos" }).click();
    expect(await dialog.locator("pre").innerText()).toBe(raw);
    expect(await page.evaluate(() => (window as any).snapshotReads)).toBe(1);
    await dialog.getByRole("button", { name: "Actualizar datos" }).click();
    expect(await page.evaluate(() => (window as any).snapshotReads)).toBe(2);
    expect(JSON.parse(await dialog.locator("pre").innerText()).timestamp).not.toBe(snapshot.timestamp);
    await consent.uncheck();
    await expect(dialog.locator("pre")).toHaveCount(0);
    await consent.check();
    await expect(dialog.getByRole("button", { name: "Ver datos técnicos" })).toHaveAttribute("aria-expanded", "false");
});

test("screenshot validation, preview and removal work on a narrow viewport", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 660 });
    const dialog = await openReporter(page);
    await dialog.getByLabel("Otro", { exact: true }).check();
    await dialog.getByRole("textbox").fill("El contenido no cabe en la pantalla pequeña.");
    const picker = dialog.getByLabel("Captura de pantalla (opcional)");
    await picker.setInputFiles({ name: "invalid.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg/>") });
    await expect(dialog.locator("[data-attachment-error]")).toContainText("hasta 5 MiB");
    await expect(dialog.getByRole("status")).toContainText("Cambia o quita la captura");
    await picker.setInputFiles({ name: "broken.png", mimeType: "image/png", buffer: Buffer.from("broken") });
    await expect(dialog.locator("[data-attachment-error]")).toContainText("No pudimos abrir");
    await picker.setInputFiles({ name: "large.png", mimeType: "image/png", buffer: Buffer.alloc(5 * 1024 * 1024 + 1) });
    await expect(dialog.locator("[data-attachment-error]")).toContainText("hasta 5 MiB");
    const png = await page.evaluate(() => {
        const canvas = document.createElement("canvas");
        canvas.width = 20; canvas.height = 20;
        return canvas.toDataURL("image/png").split(",")[1];
    });
    await picker.setInputFiles({ name: "screen.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
    await expect(dialog.getByRole("img")).toBeVisible();
    await expect(dialog.getByRole("status")).toContainText("Listo para enviar");
    const bounds = await dialog.boundingBox();
    expect(bounds!.width).toBeLessThanOrEqual(390);
    await dialog.getByRole("button", { name: "Quitar captura" }).click();
    await expect(dialog.getByRole("img")).toHaveCount(0);
    await expect(dialog.locator("[data-attachment-error]")).toBeEmpty();
    await page.screenshot({ path: testInfo.outputPath("reporter-mobile.png") });
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Configuración de Tap List" }).click();
    await page.getByRole("button", { name: "Reportar un problema", exact: true }).click();
    await dialog.click({ position: { x: 2, y: 2 } });
    await expect(dialog).not.toBeVisible();
});

test("existing settings actions, dismissal and logo hold remain available", async ({ page }) => {
    const dialog = await openReporter(page);
    await page.keyboard.press("Escape");
    const trigger = page.getByRole("button", { name: "Configuración de Tap List" });
    const panel = page.locator(".tap-list-settings__panel");
    await trigger.click();
    await page.getByRole("button", { name: "Consejos", exact: true }).click();
    await expect(panel.getByRole("heading", { name: "Vistas del Tap List" })).toBeVisible();
    await page.getByRole("button", { name: "← Ajustes" }).click();
    await page.getByRole("button", { name: "Créditos", exact: true }).click();
    await expect(panel.getByRole("heading", { name: "DESARROLLO" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
    await trigger.click();
    await page.getByRole("button", { name: "Negro", exact: true }).click();
    await expect(page.locator(".tap-list-layout")).toHaveAttribute("data-taplist-background", "black");
    await expect(panel).toHaveCount(0);
    await trigger.click();
    await page.mouse.click(2, 2);
    await expect(panel).toHaveCount(0);
    // The application's existing hold recognizer listens to native touch events.
    await trigger.dispatchEvent("touchstart", { touches: [{ identifier: 1, clientX: 100, clientY: 100 }] });
    await expect(page.locator("[data-atlas-artwork-peek]")).toBeVisible();
    await trigger.dispatchEvent("touchend", { touches: [], changedTouches: [{ identifier: 1 }] });
    await expect(dialog).not.toBeVisible();
    await page.unroute("**/api/public/tap");
    await page.route("**/api/public/tap", route => route.fulfill({ json: [
        { id: 1, name: "Test", style: "IPA", abv: 5, tap_position: 1, image_url: "" },
    ] }));
    await page.reload();
    await trigger.click();
    await page.getByRole("button", { name: "Repetir tutorial" }).click();
    // Home consumes the one-shot restart parameter after entering the tutorial.
    await expect(page).toHaveURL(/tutorial=1/);
    await expect(panel).toHaveCount(0);
    await expect(page.locator(".home-tutorial-message")).toBeVisible();
});

test("dialog follows a shrinking visual viewport without losing its draft", async ({ page }) => {
    await page.addInitScript(() => {
        const visual = new EventTarget();
        Object.assign(visual, { height: 700, width: 390, offsetTop: 0, offsetLeft: 0, scale: 1 });
        Object.defineProperty(window, "visualViewport", { configurable: true, value: visual });
    });
    const dialog = await openReporter(page);
    await dialog.getByLabel("Otro", { exact: true }).check();
    await dialog.getByRole("textbox").fill("Un borrador durante cambios de teclado.");
    await page.evaluate(() => {
        Object.assign(window.visualViewport!, { height: 350, offsetTop: 30 });
        window.visualViewport!.dispatchEvent(new Event("resize"));
    });
    await expect(dialog).toHaveCSS("height", "350px");
    await expect(dialog).toHaveCSS("top", "30px");
    await expect(dialog.getByRole("textbox")).toHaveValue("Un borrador durante cambios de teclado.");
    await dialog.getByRole("button", { name: "Cerrar reporte" }).click();
    await expect(dialog).not.toBeVisible();
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe("hidden");
});

const receipt = { report_id: "f630c3e9-90fc-4bd5-9a67-9746140daef8", stored_at: "2026-11-02T12:00:00Z" };

function reportPart(raw: string) {
    return JSON.parse(raw.match(/name="report"\r\n\r\n([^\r]+)\r\n/)![1]);
}

test("submission sends only consented data and shows success after confirmation", async ({ page }) => {
    const dialog = await openReporter(page);
    await expect(dialog).toHaveAccessibleDescription(/Cuéntanos qué ocurrió.*Evita incluir información personal/i);
    await dialog.getByLabel("Otro", { exact: true }).check();
    await dialog.getByRole("textbox").fill("  La lista tarda demasiado en aparecer.  ");
    await dialog.getByLabel("Autorizo incluir datos técnicos", { exact: false }).check();
    await dialog.getByLabel("Autorizo incluir datos técnicos", { exact: false }).uncheck();
    let release!: () => void;
    const pending = new Promise<void>(resolve => { release = resolve; });
    let sent: Record<string, unknown> | undefined;
    await page.route("**/api/public/issue-reports", async route => {
        sent = reportPart(route.request().postData()!);
        expect(route.request().headers()["authorization"]).toBeUndefined();
        await pending;
        await route.fulfill({ status: 201, json: receipt });
    });
    await dialog.getByRole("button", { name: "Enviar reporte" }).click();
    await expect(dialog.getByRole("status")).toHaveText("Enviando reporte…");
    await expect(dialog.getByRole("button", { name: "Enviando…" })).toBeDisabled();
    await expect(dialog.getByRole("textbox")).toBeDisabled();
    await expect(dialog.getByText(receipt.report_id)).toHaveCount(0);
    await expect.poll(() => sent?.diagnostic_consent).toBe(false);
    expect(sent).not.toHaveProperty("diagnostics");
    expect(sent?.description).toBe("La lista tarda demasiado en aparecer.");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Configuración de Tap List" }).click();
    await page.getByRole("button", { name: "Reportar un problema", exact: true }).click();
    await expect(dialog.getByRole("status")).toHaveText("Enviando reporte…");
    release();
    await expect(dialog.getByRole("status")).toContainText(`Reporte guardado. ID: ${receipt.report_id}`);
    await expect(dialog.getByRole("status")).toBeFocused();
    await dialog.getByRole("button", { name: "Enviar otro reporte" }).click();
    await expect(dialog.getByRole("textbox")).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Enviar reporte" })).toBeDisabled();
});

test("network and server failures retain the draft and reuse its key until content changes", async ({ page }) => {
    const dialog = await openReporter(page);
    await dialog.getByLabel("Otro", { exact: true }).check();
    const description = dialog.getByRole("textbox");
    await description.fill("La lista no aparece en mi navegador.");
    const sent: Array<Record<string, unknown>> = [];
    let attempt = 0;
    await page.route("**/api/public/issue-reports", async route => {
        sent.push(reportPart(route.request().postData()!));
        attempt++;
        if (attempt === 1) return route.abort("failed");
        const status = [0, 0, 429, 503, 422, 200][attempt];
        await route.fulfill({ status, headers: { "Retry-After": "30" }, json: status === 200 ? receipt : { detail: "error" } });
    });
    for (const message of ["No pudimos conectar", "Espera 30 segundos", "No pudimos confirmar", "Revisa las categorías"]) {
        await dialog.getByRole("button", { name: "Enviar reporte" }).click();
        await expect(dialog.locator("[data-submission-error]")).toContainText(message);
        await expect(description).toHaveValue("La lista no aparece en mi navegador.");
        await expect(dialog.getByText(receipt.report_id)).toHaveCount(0);
    }
    expect(new Set(sent.map(item => item.idempotency_key)).size).toBe(1);
    await description.fill("La lista ahora aparece pero tiene otro problema.");
    await dialog.getByRole("button", { name: "Enviar reporte" }).click();
    await expect(dialog.getByRole("status")).toContainText(receipt.report_id);
    expect(sent[4].idempotency_key).not.toBe(sent[0].idempotency_key);
});

test("timeout retries keep key, screenshot and diagnostic snapshot", async ({ page }) => {
    const dialog = await openReporter(page);
    await dialog.getByLabel("Otro", { exact: true }).check();
    await dialog.getByRole("textbox").fill("La pantalla muestra un problema al cargar.");
    await dialog.getByLabel("Autorizo incluir datos técnicos", { exact: false }).check();
    const png = await page.evaluate(() => document.createElement("canvas").toDataURL().split(",")[1]);
    await dialog.getByLabel("Captura de pantalla (opcional)").setInputFiles({
        name: "screenshot.png", mimeType: "image/png", buffer: Buffer.from(png, "base64"),
    });
    await expect(dialog.getByRole("button", { name: "Enviar reporte" })).toBeEnabled();
    const sent: Array<Record<string, unknown>> = [];
    let release!: () => void;
    const pending = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/api/public/issue-reports", async route => {
        const raw = route.request().postDataBuffer()!.toString("utf8");
        expect(raw).toContain('name="screenshot"');
        sent.push(reportPart(raw));
        if (sent.length === 1) {
            await pending;
            await route.abort().catch(() => {});
        } else await route.fulfill({ status: 200, json: receipt });
    });
    await page.clock.install();
    await dialog.getByRole("button", { name: "Enviar reporte" }).click();
    await expect.poll(() => sent.length).toBe(1);
    await page.clock.fastForward(20_001);
    await expect(dialog.locator("[data-submission-error]")).toContainText("La respuesta tardó demasiado");
    release();
    await dialog.getByRole("button", { name: "Enviar reporte" }).click();
    await expect(dialog.getByRole("status")).toContainText(receipt.report_id);
    expect(sent[0]).toEqual(sent[1]);
    expect(sent[1].diagnostic_consent).toBe(true);
    expect(sent[1].diagnostics).toHaveProperty("route", "/");
});

test("an unconfirmed receipt never shows success and a retry keeps the same key", async ({ page }) => {
    const dialog = await openReporter(page);
    await dialog.getByLabel("Otro", { exact: true }).check();
    await dialog.getByRole("textbox").fill("No se puede cambiar el orden de las cervezas.");
    const keys: string[] = [];
    await page.route("**/api/public/issue-reports", async route => {
        keys.push(reportPart(route.request().postData()!).idempotency_key);
        await route.fulfill({ status: 200, json: keys.length === 1 ? { success: true } : receipt });
    });
    await dialog.getByRole("button", { name: "Enviar reporte" }).click();
    await expect(dialog.locator("[data-submission-error]")).toContainText("No pudimos confirmar");
    await expect(dialog.getByText("Reporte guardado", { exact: false })).toHaveCount(0);
    await dialog.getByRole("button", { name: "Enviar reporte" }).click();
    await expect(dialog.getByRole("status")).toContainText(receipt.report_id);
    expect(keys[0]).toBe(keys[1]);
});


test("category labels preserve API values and submitted diagnostics match the preview", async ({ page }) => {
    const dialog = await openReporter(page);
    await dialog.getByLabel("Información de una cerveza", { exact: true }).check();
    await dialog.getByLabel("Uso o apariencia", { exact: true }).check();
    await dialog.getByRole("textbox").fill("La información y los controles no se muestran bien.");
    await dialog.getByLabel("Autorizo incluir datos técnicos", { exact: false }).check();
    await dialog.getByRole("button", { name: "Ver datos técnicos" }).click();
    const snapshot = JSON.parse(await dialog.locator("pre").innerText());
    await dialog.getByRole("button", { name: "Ocultar datos técnicos" }).click();
    let sent: Record<string, unknown> | undefined;
    await page.route("**/api/public/issue-reports", async route => {
        sent = reportPart(route.request().postData()!);
        await route.fulfill({ status: 201, json: receipt });
    });
    await dialog.getByRole("button", { name: "Enviar reporte" }).click();
    await expect(dialog.getByRole("status")).toContainText("Reporte guardado. ID:");
    expect(sent?.categories).toEqual(["Información de cerveza", "Interacción / visualización"]);
    expect(sent?.diagnostic_consent).toBe(true);
    expect(sent?.diagnostics).toEqual(snapshot);
});
