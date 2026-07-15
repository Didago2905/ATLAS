/**
 * ==========================================================
 * Museum Engine
 * Archive
 * Version: 2.0
 *
 * Purpose
 * Maintain the canonical historical collection.
 *
 * Owns
 * Artwork identity, historical metadata, and permanent records.
 *
 * Never Owns
 * Navigation, selection, viewport, scene, animation, or renderer concerns.
 *
 * QA Observes
 * Canonical identity, historical integrity, and record permanence.
 *
 * Dependencies
 * None. This engine is the collection authority.
 *
 * Notes
 * Archive data remains independent of experience and platform concerns.
 * ==========================================================
 */

export const ENGINE_NAME = "Archive";

/**
 * Creates the archive collection.
 *
 * V1:
 * Returns the artworks in their original order.
 *
 * Future versions may apply:
 * - Timeline
 * - Filters
 * - Curated exhibitions
 * - Collections
 */
export function createArchive(artworks = []) {
    return [...artworks];
}