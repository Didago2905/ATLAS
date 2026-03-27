export function parseBeerText(text) {
    if (!text) return null;

    const clean = text.trim();

    function extractBreweryAndOrigin(text) {
        let brewery = "";
        let origin = "";

        // 🔥 1. Detectar cervecería invitada
        const match = text.match(/CERVECER[IÍ]A INVITADA:\s*([^\.]+)\./i);

        if (match && match[1]) {
            const raw = match[1].trim();
            const parts = raw.split(",").map(p => p.trim());

            brewery = parts[0] || "";

            if (parts.length > 1) {
                origin = parts.slice(1).join(", ");
            }

            return { brewery, origin };
        }

        // 🔥 2. Detectar Tiburón (cerveza de casa)
        if (/tibur[oó]n/i.test(text)) {
            return {
                brewery: "Tiburón",
                origin: "Xalapa,Ver."
            };
        }

        // 🔥 3. fallback limpio (sin inventar datos)
        return { brewery: "", origin: "" };
    }

    // 🔥 DETECTAR FORMATO NUEVO (solo cuando está completamente estructurado)
    const isNewFormat =
        clean.includes("🍺") &&
        /estilo:/i.test(clean) &&
        /abv:/i.test(clean);

    // =================================================
    // 🧠 PARSER NUEVO (FORMATO NORMALIZADO)
    // =================================================
    if (isNewFormat) {

        const lines = clean
            .split("\n")
            .map(l => l.trim())
            .filter(l => l.length > 0);

        const { brewery, origin } = extractBreweryAndOrigin(clean);

        const beer = {
            name: "",
            brewery,
            origin,
            style: "",
            abv: null,
            color: "",
            description: "",
            prices: {}
        };

        let mode = null;

        for (let line of lines) {

            // 🍺 NOMBRE
            if (line.startsWith("🍺")) {
                let rawName = line.replace("🍺", "").trim();

                // 🔥 cortar si viene ESTILO en la misma línea
                if (/ESTILO:/i.test(rawName)) {
                    rawName = rawName.split(/ESTILO:/i)[0].trim();
                }

                beer.name = rawName;
                continue;
            }

            // ESTILO
            if (/^ESTILO:/i.test(line)) {
                let rawStyle = line.split(":")[1]?.trim() || "";

                // 🔥 cortar ruido (ABV / ALC / COLOR / números con %)
                rawStyle = rawStyle
                    .split(/ABV|ALC|COLOR/i)[0]
                    .split(/\d+(\.\d+)?%/)[0] // 🔥 corta "5.0%"
                    .replace(/\.+$/, "")
                    .trim();

                beer.style = rawStyle;
                continue;
            }

            // ABV
            if (/^ABV:/i.test(line)) {
                const match = line.match(/[\d.]+/);
                beer.abv = match ? parseFloat(match[0]) : null;
                continue;
            }

            // COLOR
            if (/^COLOR:/i.test(line)) {
                beer.color = line.split(":")[1]?.trim() || "";
                continue;
            }

            // PRECIOS
            if (/^PRECIOS:/i.test(line)) {
                mode = "prices";
                continue;
            }

            if (mode === "prices") {

                // 🔥 SI ENTRA DESCRIPCIÓN → CAMBIAR DE MODO
                if (/^DESCRIPCI[oÓ]N:/i.test(line)) {
                    mode = "description";
                    beer.description = line.split(":")[1]?.trim() || "";
                    continue;
                }

                if (line.includes(":")) {
                    const [label, value] = line.split(":");

                    const key = label.toLowerCase().replace(/\s+/g, "_");
                    const num = parseFloat(value.trim());

                    if (!isNaN(num)) {
                        beer.prices[key] = num;
                    }
                }

                continue;
            }

            // DESCRIPCIÓN
            if (/^DESCRIPCI[oÓ]N:/i.test(line)) {
                mode = "description";
                beer.description = line.split(":")[1]?.trim() || "";
                continue;
            }

            if (mode === "description") {
                beer.description += (beer.description ? " " : "") + line;
            }
        }

        return beer;
    }

    // =================================================
    // 🧱 PARSER ORIGINAL (MEJORADO)
    // =================================================

    let brewery = "Tiburón";
    let origin = "Xalapa,Ver.";

    const breweryMatch = clean.match(/CERVECER[IÍ]A INVITADA:\s*([^\.]+)\./i);

    if (breweryMatch && breweryMatch[1]) {
        const raw = breweryMatch[1].trim();
        const parts = raw.split(",").map(p => p.trim());

        brewery = parts[0] || "Tiburón";

        if (parts.length > 1) {
            origin = parts.slice(1).join(", ");
        }
    }

    // 🔥 NORMALIZAR PRECIOS (soporte para "/")
    const normalized = clean.replace(/\s*\/\s*/g, "\n");

    const tasterMatch = normalized.match(/TASTER\s*\$(\d+)/i);
    const smallMatch = normalized.match(/PINTA CHICA\s*\$(\d+)/i);
    const mediumMatch = normalized.match(/PINTA GRANDE\s*\$(\d+)/i);
    const largeMatch = normalized.match(/JARRA CHICA\s*\$(\d+)/i);
    const jarraGrandeMatch = normalized.match(/JARRA GRANDE\s*\$(\d+)/i);

    const styleMatch = clean.match(/ESTILO:\s*([^.]+)\./i);
    const abvMatch = clean.match(/([\d.]+)%\s*ALC/i);

    const colorMatch = clean.match(/COLOR:\s*([^]+?)(?=TASTER|PINTA|JARRA|\$|ESTILO:|$)/i);

    let name = "";

    let temp = clean.replace(/CERVECER[IÍ]A INVITADA:[^.]+\./i, "");

    // 🔥 FIX CRÍTICO (regex robusto)
    temp = temp.replace(/TASTER\s*\$\d+[\s\S]*?JARRA GRANDE\s*\$\d+/i, "");

    const nameMatch = temp.match(/^(.*?)\s+ESTILO:/i);

    if (nameMatch && nameMatch[1]) {
        name = nameMatch[1].trim();
    }

    if (!name) {
        name = styleMatch ? styleMatch[1].trim() : "Cerveza";
    }

    let description = clean;

    description = description.replace(/CERVECER[IÍ]A INVITADA:[^.]+\./i, "");
    description = description.replace(/TASTER\s*\$\d+[\s\S]*?JARRA GRANDE\s*\$\d+/i, "");
    description = description.replace(/.*?ESTILO:[^.]+\./i, "");
    description = description.replace(/[\d.]+%\s*ALC.*?COLOR:[^.]+\./i, "");

    description = description.trim();

    return {
        name,
        brewery,
        origin,
        style: styleMatch ? styleMatch[1].trim() : "",
        abv: abvMatch ? parseFloat(abvMatch[1]) : null,
        color: colorMatch ? colorMatch[1].trim() : "",

        prices: {
            taster: tasterMatch ? parseInt(tasterMatch[1]) : null,
            pinta_chica: smallMatch ? parseInt(smallMatch[1]) : null,
            pinta_grande: mediumMatch ? parseInt(mediumMatch[1]) : null,
            jarra_chica: largeMatch ? parseInt(largeMatch[1]) : null,
            jarra_grande: jarraGrandeMatch ? parseInt(jarraGrandeMatch[1]) : null
        },

        description
    };
}


// 🔥 MULTIPARSER (ESTABLE)
export function parseMultipleBeers(text) {
    if (!text) return [];

    const blocks = text
        .split("🍺")
        .map(b => b.trim())
        .filter(b => b.length > 0);

    const beers = [];

    blocks.forEach((block, index) => {
        try {

            // 🔥 aseguramos que cada bloque tenga encabezado correcto
            const normalizedBlock = block.startsWith("🍺")
                ? block
                : "🍺 " + block;

            const parsed = parseBeerText(normalizedBlock);

            if (parsed && parsed.name) {
                beers.push(parsed);
            }

        } catch (err) {
            console.warn("❌ Error en bloque", index);
        }
    });

    console.log("🧱 BLOQUES:", blocks.length);
    console.log("🍺 BEERS:", beers.length);

    return beers;
}