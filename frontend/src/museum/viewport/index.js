/**
 * ==========================================================
 * Museum Engine
 * Viewport
 * Version: 2.0
 *
 * Purpose
 * Describe the visible presentation space.
 *
 * Owns
 * Visible area, orientation, safe areas, presentation mode, container width, and resize observation.
 *
 * Never Owns
 * Selection, navigation, scene, animation, or renderer concerns.
 *
 * QA Observes
 * Presentation-space accuracy across orientation and safe-area changes.
 *
 * Dependencies
 * Platform display characteristics and container elements are provided by the host environment.
 *
 * Notes
 * Viewport describes presentation constraints without calculating a scene.
 * ==========================================================
 */

export const ENGINE_NAME = "Viewport";
/**
 * Reads the current presentation-space measurements.
 */
export function getViewport(container) {
    return {
        isLandscape: window.innerWidth > window.innerHeight,
        visibleWidth: window.visualViewport?.width || window.innerWidth,
        visibleHeight: window.visualViewport?.height || window.innerHeight,
        containerWidth: container?.offsetWidth || 0,
    };
}

/**
 * Observes platform resize events for viewport consumers.
 */
export function observeViewport(onResize) {
    window.addEventListener("resize", onResize);

    return () => {
        window.removeEventListener("resize", onResize);
    };
}