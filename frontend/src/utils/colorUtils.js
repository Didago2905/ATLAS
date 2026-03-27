// 🔧 helper primero (🔥 importante)
const capitalize = (str) =>
    str.charAt(0).toUpperCase() + str.slice(1);

// 🔥 Fuente de verdad
export const colorMap = {
    // 🟡 claros / lagers
    amarillo: "#e6b800",
    dorado: "#e6b800",
    dorada: "#e6b800",
    amarillo_brillante: "#f4d03f",
    amarillo_palido: "#f7dc6f",

    // 🟠 ámbar / intermedios
    ambar: "#d88c00",
    amber: "#d88c00",
    cobrizo: "#b87333",
    rojizo: "#a93226",

    // 🟤 maltosos
    marron: "#6e2c00",
    cafe: "#6e2c00",
    cafe_oscuro: "#3e2723",

    // ⚫ oscuros
    oscuro: "#1c1c1c",
    negro: "#111111",

    // 🔴 especiales
    rojo: "#8b3a3a",
    rosa: "#ff2b5b"
};

// 🔁 derivado automático
export const colorLabelMap = Object.fromEntries(
    Object.entries(colorMap).map(([k, v]) => [v, capitalize(k.replace("_", " "))])
);

// 🔧 normalize
export const normalizeColor = (color) => {
    if (!color) return "";

    return color
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/\.+$/, "") // 🔥 quitar puntos finales
        .trim()
        .replace(/\s+/g, "_"); // 🔥 clave para "cafe oscuro"
};

// 🔧 resolver color
export const resolveColor = (rawColor) => {
    if (!rawColor) return "#888888";

    const cleaned = rawColor.trim();

    // 🔥 si ya es HEX → usar directo
    if (/^#([0-9A-F]{3}){1,2}$/i.test(cleaned)) {
        return cleaned;
    }

    const normalized = normalizeColor(cleaned);

    const match = Object.keys(colorMap).find(key =>
        normalized.includes(key) || key.includes(normalized)
    );

    return match ? colorMap[match] : "#888888";
};