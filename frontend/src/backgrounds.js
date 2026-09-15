export const TAP_BACKGROUNDS = Object.freeze([
    Object.freeze({
        id: "black",
        label: "Negro",
        value: "#000000",
    }),
    Object.freeze({
        id: "gallery-light",
        label: "Galería clara",
        value: "radial-gradient(ellipse at center, #F0EDE6 0%, #E4DED3 50%, #CEC8BE 100%)",
    }),
    Object.freeze({
        id: "petrol",
        label: "Petróleo",
        value: "radial-gradient(ellipse at center, #34464D 0%, #1B292F 38%, #0A1114 70%, #000000 100%)",
    }),
    Object.freeze({
        id: "burgundy",
        label: "Borgoña",
        value: "radial-gradient(ellipse at center, #593039 0%, #351D23 42%, #160B0F 72%, #000000 100%)",
    }),
]);

export function resolveTapBackground(id) {
    return TAP_BACKGROUNDS.find(background => background.id === id) || TAP_BACKGROUNDS[0];
}
