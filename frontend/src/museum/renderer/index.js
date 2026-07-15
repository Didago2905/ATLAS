/**
 * ==========================================================
 * Museum Engine
 * Renderer
 * Version: 2.0
 *
 * Purpose
 * Materialize the experience on the current platform.
 *
 * Owns
 * Rendering, platform implementation, and performance optimization.
 *
 * Never Owns
 * Application state, selection, navigation, viewport, scene, or animation concerns.
 *
 * QA Observes
 * Platform fidelity, rendering performance, and implementation stability.
 *
 * Dependencies
 * Platform capabilities and experience contracts are provided externally.
 *
 * Notes
 * Renderer implements the experience without defining its state or behavior.
 * ==========================================================
 */

export const ENGINE_NAME = "Renderer";