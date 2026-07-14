import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
    testDir: "./tests",

    timeout: 30_000,

    outputDir: "./tests/results",

    use: {
        baseURL: "http://127.0.0.1:5173",

        headless: true,

        screenshot: "only-on-failure",

        trace: "retain-on-failure",
    },

    projects: [
        {
            name: "webkit",
            use: {
                ...devices["Desktop Safari"],
            },
        },
    ],
});