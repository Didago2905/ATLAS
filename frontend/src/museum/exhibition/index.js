/**
 * ==========================================================
 * Museum Engine
 * Exhibition
 * Version: 2.0
 *
 * Purpose
 * Transform the archive into a curated experience.
 *
 * Owns
 * Narrative, ordering, galleries, and curatorial context.
 *
 * Never Owns
 * Archive storage, selection, viewport, scene, animation, or renderer concerns.
 *
 * QA Observes
 * Curatorial coherence, ordering, and gallery context.
 *
 * Dependencies
 * Archive is its source of historical collection material.
 *
 * Notes
 * Curation interprets the collection without changing its canonical record.
 * ==========================================================
 */

export const ENGINE_NAME = "Exhibition";

/**
 * Creates the exhibition order.
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
export function createExhibition(artworks = []) {
    return [...artworks];
}