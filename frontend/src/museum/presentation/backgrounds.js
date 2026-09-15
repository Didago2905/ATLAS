import { TAP_BACKGROUNDS } from "../../backgrounds";

export const MUSEUM_BACKGROUND_STORAGE_KEY = "atlas_museum_background";

export const MUSEUM_BACKGROUNDS = TAP_BACKGROUNDS;

const MUSEUM_BACKGROUND_ALIASES = Object.freeze({
    bone: "gallery-light",
    "dark-gradient": "petrol",
    "sand-gradient": "burgundy",
});

export function resolveMuseumBackground(id) {
    const canonicalId = MUSEUM_BACKGROUND_ALIASES[id] || id;

    return MUSEUM_BACKGROUNDS.find(background => background.id === canonicalId)
        || MUSEUM_BACKGROUNDS[0];
}
