export function parseBeerText(text) {
    if (!text) return null;

    const clean = text.replace(/\n+/g, " ").trim();

    // 🔹 NAME (antes de ESTILO)
    const nameMatch = clean.match(/^(.*?)\s+ESTILO:/i);

    // 🔹 STYLE
    const styleMatch = clean.match(/ESTILO:\s*([^.]+)\./i);

    // 🔹 ABV
    const abvMatch = clean.match(/([\d.]+)%\s*ALC/i);

    // 🔹 COLOR
    const colorMatch = clean.match(/COLOR:\s*([^.]+)\.?/i);

    // 🔹 PRECIOS
    const tasterMatch = clean.match(/TASTER\s*\$(\d+)/i);
    const smallMatch = clean.match(/PINTA CHICA\s*\$(\d+)/i);
    const mediumMatch = clean.match(/PINTA GRANDE\s*\$(\d+)/i);
    const largeMatch = clean.match(/JARRA CHICA\s*\$(\d+)/i);

    // 🔹 DESCRIPCIÓN (todo después de precios)
    const descriptionMatch = clean.split(/JARRA GRANDE\s*\$\d+/i)[1];

    return {
        name: nameMatch ? nameMatch[1].trim() : "",
        style: styleMatch ? styleMatch[1].trim() : "",
        abv: abvMatch ? parseFloat(abvMatch[1]) : null,
        color: colorMatch ? colorMatch[1].trim() : "",

        prices: {
            taster: tasterMatch ? parseInt(tasterMatch[1]) : null,
            pinta_chica: smallMatch ? parseInt(smallMatch[1]) : null,
            pinta_grande: mediumMatch ? parseInt(mediumMatch[1]) : null,
            jarra_chica: largeMatch ? parseInt(largeMatch[1]) : null,
            jarra_grande: (() => {
                const match = clean.match(/JARRA GRANDE\s*\$(\d+)/i);
                return match ? parseInt(match[1]) : null;
            })()
        },

        description: descriptionMatch ? descriptionMatch.trim() : ""
    };
}