/**
 * ==========================================================
 * Museum Engine
 * Navigation
 * Version: 2.0
 *
 * Purpose
 * Interpret visitor intent.
 *
 * Owns
 * Navigation commands and exploration flow.
 *
 * Never Owns
 * Selection, viewport, scene, animation, or renderer concerns.
 *
 * QA Observes
 * Command interpretation and coherent exploration flow.
 *
 * Dependencies
 * Visitor intent is provided by the interaction boundary.
 *
 * Notes
 * Navigation expresses intent; it does not materialize the experience.
 * ==========================================================
 */

export const ENGINE_NAME = "Navigation";

/**
 * Canonical Museum navigation modes.
 */
export const MUSEUM_MODES = {
    FICHAS: "fichas",
    TAP: "tap",
};

/**
 * Interpret the visitor's navigation intent.
 * Navigation owns the transition value only.
 */
export function selectMuseumMode(mode) {
    return mode;
}
/**
 * Interprets artwork interaction from measured geometry.
 */
export function resolveArtworkNavigation(elementCenter, centerX) {
    const distance = elementCenter - centerX;

    if (Math.abs(distance) > 10) {
        return "center";
    }

    return "activate";
}