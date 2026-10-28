import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { uploadImage, uploadTapImage, tapUploadMessage } from "../src/api/upload.js";

const originals = { fetch: globalThis.fetch, localStorage: globalThis.localStorage, window: globalThis.window };
beforeEach(() => {
    globalThis.localStorage = { getItem: () => "test-token", removeItem: () => {} };
    globalThis.window = { location: { href: "" } };
});
afterEach(() => Object.assign(globalThis, originals));
const file = () => new Blob(["synthetic upload"], { type: "image/jpeg" });
const response = (status, data) => ({ status, ok: status < 400, json: async () => data });

test("Tap upload sends one request and confirms both publication targets", async () => {
    const payload = { operational_updated: true, historical_archived: true, historical_created: true };
    let calls = 0;
    globalThis.fetch = async (url, options) => {
        calls++;
        assert.equal(url, "/api/admin/beers/7/upload-image");
        assert.equal(options.headers.Authorization, "Bearer test-token");
        assert.equal([...options.body.keys()].join(","), "file");
        return response(200, payload);
    };
    assert.deepEqual(await uploadTapImage(7, file()), payload);
    assert.equal(calls, 1);
    assert.match(tapUploadMessage(payload), /operativa actualizada.*histórica archivada/);
});

test("A repeated upload reports existing history without claiming a new artwork", async () => {
    const payload = { operational_updated: true, historical_archived: true, historical_created: false };
    globalThis.fetch = async () => response(200, payload);
    assert.match(tapUploadMessage(await uploadTapImage(7, file())), /ya archivada; sin duplicados/);
});

test("Partial confirmation cannot be reported as complete success", async () => {
    globalThis.fetch = async () => response(200, { operational_updated: true, historical_archived: false });
    await assert.rejects(uploadTapImage(7, file()), /ambos destinos/);
});

test("Publication failures preserve the server error in Admin feedback", async () => {
    globalThis.fetch = async () => response(500, { detail: "Previous publication restored" });
    await assert.rejects(uploadTapImage(7, file()), /Previous publication restored/);
});

test("Expired sessions redirect and reject instead of returning a false success", async () => {
    globalThis.fetch = async () => response(401, {});
    await assert.rejects(uploadTapImage(7, file()), /Sesión expirada/);
    assert.equal(window.location.href, "/login");
    await assert.rejects(uploadImage(file(), "tap", {}), /Sesión expirada/);
});

test("Historical uploader retains metadata and reports validation errors", async () => {
    globalThis.fetch = async (url, options) => {
        assert.equal(url, "/api/admin/museum");
        assert.equal(options.body.get("type"), "packaging");
        assert.equal(options.body.get("name"), "Approved packaging");
        return response(400, { detail: "Invalid image data" });
    };
    await assert.rejects(uploadImage(file(), "packaging", { name: "Approved packaging" }), /Invalid image data/);
});
