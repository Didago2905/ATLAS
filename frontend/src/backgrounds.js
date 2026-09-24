export const TAP_BACKGROUNDS = Object.freeze([
    Object.freeze({
        id: "black",
        label: "Negro",
        value: "#000000",
    }),
    Object.freeze({
        id: "gallery-light",
        label: "Galería clara",
        value: "radial-gradient(ellipse at center, #F0EDE6 0%, #E4DED3 50%, #CEC8BE 100%)",
    }),
    Object.freeze({
        id: "petrol",
        label: "Petróleo",
        value: "radial-gradient(ellipse at center, #34464D 0%, #1B292F 38%, #0A1114 70%, #000000 100%)",
    }),
    Object.freeze({
        id: "burgundy",
        label: "Borgoña",
        value: "radial-gradient(ellipse at center, #593039 0%, #351D23 42%, #160B0F 72%, #000000 100%)",
    }),
]);

export const BACKGROUND_STORAGE_KEY = "atlas_background";
export const DEFAULT_BACKGROUND_ID = "burgundy";

const BACKGROUND_ALIASES = Object.freeze({
    bone: "gallery-light",
    "dark-gradient": "petrol",
    "sand-gradient": "burgundy",
});

function findBackground(id) {
    const canonicalId = Object.hasOwn(BACKGROUND_ALIASES, id) ? BACKGROUND_ALIASES[id] : id;
    return TAP_BACKGROUNDS.find(background => background.id === canonicalId);
}

export function resolveTapBackground(id) {
    return findBackground(id) || findBackground(DEFAULT_BACKGROUND_ID);
}

export function writeBackgroundPreference(id) {
    const background = resolveTapBackground(id);
    try {
        localStorage.setItem(BACKGROUND_STORAGE_KEY, background.id);
    } catch {
        // Storage may be unavailable; the caller can still use the resolved preset.
    }
    return background;
}

export function readBackgroundPreference() {
    for (const key of [BACKGROUND_STORAGE_KEY, "atlas_taplist_background", "atlas_museum_background"]) {
        let id;
        try {
            id = localStorage.getItem(key);
        } catch {
            continue;
        }
        const background = findBackground(id);
        if (background) return writeBackgroundPreference(background.id);
    }
    return writeBackgroundPreference(DEFAULT_BACKGROUND_ID);
}
