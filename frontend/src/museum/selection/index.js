/**
 * ==========================================================
 * Museum Engine
 * Selection
 * Version: 2.0
 *
 * Purpose
 * Maintain exactly one active artwork.
 *
 * Owns
 * The active artwork and its selection context.
 *
 * Never Owns
 * Geometry, DOM, scroll, animation, or renderer concerns.
 *
 * QA Observes
 * The single-active-artwork invariant and selection context.
 *
 * Dependencies
 * Artwork identity is supplied by the collection domain.
 *
 * Notes
 * Selection is application state, not a visual implementation detail.
 * ==========================================================
 */

export const ENGINE_NAME = "Selection";
/**
 * Selects the active artwork.
 */
export function selectArtwork(artwork) {
    return artwork;
}

/**
 * Clears the active artwork.
 */
export function clearSelection() {
    return null;
}