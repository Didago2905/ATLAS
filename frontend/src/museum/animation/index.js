/**
 * ==========================================================
 * Museum Engine
 * Animation
 * Version: 2.1
 *
 * Purpose
 * -------
 * Express visual hierarchy through motion.
 *
 * Owns
 * -------
 * Visual transitions.
 * Visual continuity.
 * Visual calculations.
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
 * Animation receives geometry from Presentation
 * and returns visual state.
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

/**
 * Creates an Animation engine instance.
 *
 * The engine owns visual continuity and
 * visual state calculations.
 */
export function createAnimation() {

    let lastRotate = 0;
    let lastScale = 0;
    let lastZ = 0;

    function update({
        cardCenterX,
        viewportCenterX,
        card,
        image,
        highlight,
    }) {

        const distance = cardCenterX - viewportCenterX;
        const normalized = distance / viewportCenterX;

        const intensity = Math.min(Math.abs(normalized), 1);

        let rotate = Math.round(normalized * 40);

        if (Math.abs(normalized) < 0.03) {
            rotate = 0;
        } else {
            rotate = Math.round(rotate / 2) * 2;
        }

        let scale = 1 - intensity * 0.24;
        scale = Math.round(scale * 1000) / 1000;

        const translateZ =
            Math.round((-intensity * 60) / 10) * 10;

        const opacity = 1 - Math.min(intensity * 0.5, 0.5);

        let blur = 0;
        if (intensity > 0.6) blur = 1;
        else if (intensity > 0.35) blur = 0.5;

        const highlightStrength = 1 - intensity;
        const highlightOpacity =
            Math.round((highlightStrength * 0.20) * 100) / 100;

        let shading = 0;

        if (normalized > 0.35) shading = 0.20;
        else if (normalized > 0.1) shading = 0.10;
        else if (normalized < -0.35) shading = -0.20;
        else if (normalized < -0.1) shading = -0.10;

        const changed =
            Math.abs(rotate - lastRotate) > 0.5 ||
            Math.abs(scale - lastScale) > 0.002 ||
            Math.abs(translateZ - lastZ) > 1;

        if (changed) {
            card.style.transform = `
                perspective(900px)
                translateZ(${translateZ}px)
                rotateY(${rotate}deg)
                scale(${scale})
            `;

            lastRotate = rotate;
            lastScale = scale;
            lastZ = translateZ;
        }

        card.style.opacity = opacity;

        // blur directo
        if (image) {
            image.style.filter = `blur(${blur}px)`;
        }

        // highlight directo
        if (highlight) {
            highlight.style.opacity = highlightOpacity;
        }
    }

    return {
        update,
    };
}
