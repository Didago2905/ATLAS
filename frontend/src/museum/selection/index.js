/**
 * ==========================================================
 * Museum Engine
 * Selection
 * Version: 2.0
 *
 * Purpose
 * ----------------------------------------------------------
 * Maintain the semantic selection state of the Museum.
 *
 * Selection guarantees that at most one artwork is selected
 * at any time.
 *
 * Owns
 * ----------------------------------------------------------
 * The currently selected artwork.
 *
 * Selection represents confirmed user intent.
 *
 * Never Owns
 * ----------------------------------------------------------
 * Focus state.
 * Geometry.
 * DOM nodes.
 * Rendering.
 * Animation.
 * Browser APIs.
 * Scroll position.
 * Viewport state.
 *
 * QA Observes
 * ----------------------------------------------------------
 * Exactly zero or one artwork may be selected.
 *
 * Selection never owns focus.
 *
 * Selection never performs rendering.
 *
 * Selection never mutates presentation state.
 *
 * Dependencies
 * ----------------------------------------------------------
 * Artwork identity is supplied by the collection domain.
 *
 * Activation requests are supplied by Navigation.
 *
 * Presentation consumes the selected artwork.
 *
 * Museum coordinates Selection with the remaining engines.
 *
 * Notes
 * ----------------------------------------------------------
 * Focus and Selection are different concepts.
 *
 * Navigation determines where the user's attention is.
 *
 * Selection represents an explicit activation performed by
 * the user.
 *
 * Selection is application state, not a visual
 * implementation detail.
 * ==========================================================
 */

export const ENGINE_NAME = "Selection";

/**
 * Creates a Selection engine instance.
 */
export function createSelection() {
    let activeArtwork = null;

    /**
     * Selects an artwork.
     *
     * Stores the current application-level selection.
     */
    function selectArtwork(artwork) {
        activeArtwork = artwork;
        return activeArtwork;
    }

    /**
     * Clears the current artwork selection.
     */
    function clearSelection() {
        activeArtwork = null;
        return activeArtwork;
    }

    return {
        selectArtwork,
        clearSelection,
    };
}