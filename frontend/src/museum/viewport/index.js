/**
 * ==========================================================
 * Museum Engine
 * Viewport
 * Version: 2.0
 *
 * Purpose
 * Describe normalized presentation-space measurements.
 *
 * Owns
 * Orientation, viewport dimensions, visible presentation
 * dimensions, and normalized stage dimensions.
 *
 * Never Owns
 * Browser APIs, DOM references, event listeners, React state,
 * rendering, animation, navigation, selection, or Museum
 * presentation policy.
 *
 * Dependencies
 * Runtime supplies raw browser and stage measurements.
 * ==========================================================
 */

export const ENGINE_NAME = "Viewport";

/**
 * Normalizes raw viewport measurements.
 */
export function getViewport({
    width,
    height,
    visibleWidth = width,
    visibleHeight = height,
}) {
    return {
        isLandscape: width > height,
        width,
        height,
        visibleWidth,
        visibleHeight,
    };
}

/**
 * Normalizes raw stage measurements.
 */
export function getStageDimensions(width) {
    return {
        width,
    };
}