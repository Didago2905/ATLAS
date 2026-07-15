/**
 * ==========================================================
 * Museum Engine
 * Animation
 * Version: 2.0
 *
 * Purpose
 * -------
 * Express visual hierarchy through motion.
 *
 * Owns
 * -------
 * Visual transitions only.
 *
 * Never Owns
 * -------
 * Navigation
 * Selection
 * Viewport
 * Scene
 * Presentation
 *
 * QA Observes
 * -------
 * Transition continuity and visual consistency.
 *
 * Dependencies
 * -------
 * Animation receives state transitions from Museum.
 *
 * Notes
 * -------
 * Animation expresses state changes.
 * It never decides when or why they happen.
 * ==========================================================
 */

export const ENGINE_NAME = "Animation";

/**
 * Hide UI controls.
 *
 * V1:
 * Only changes visibility.
 */
export function hideControls(setVisible) {
    setVisible(false);
}

/**
 * Show UI controls.
 *
 * V1:
 * Only changes visibility.
 */
export function showControls(setVisible) {
    setVisible(true);
}