/**
 * ==========================================================
 * Museum Engine
 * Scene
 * Version: 2.0
 *
 * Purpose
 * Compose the moving window around the active artwork.
 *
 * Owns
 * The scene window, composition, and visual neighborhood.
 *
 * Never Owns
 * Selection, viewport calculations, animation, or renderer concerns.
 *
 * QA Observes
 * Composition and continuity of the visual neighborhood.
 *
 * Dependencies
 * The active artwork is supplied by Selection.
 *
 * Notes
 * Scene composition describes what surrounds the focus, not how it moves.
 * ==========================================================
 */

export const ENGINE_NAME = "Scene";