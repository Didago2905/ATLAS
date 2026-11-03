export function createReportKey() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function submitIssueReport(report, screenshot, key, { timeoutMs = 20_000 } = {}) {
    const body = new FormData();
    body.append("report", JSON.stringify({ ...report, idempotency_key: key }));
    if (screenshot) body.append("screenshot", screenshot, "screenshot");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetch("/api/public/issue-reports", {
            method: "POST", body, credentials: "omit", signal: controller.signal,
        });
        if (!response.ok) {
            const messages = {
                400: "Revisa el formulario y la captura antes de volver a enviar.",
                409: "No pudimos aceptar esta versión del reporte. Tu borrador sigue aquí.",
                413: "El reporte es demasiado grande. Reduce o quita la captura.",
                415: "La captura no es válida. Elige una imagen JPG, PNG o WebP.",
                422: "Revisa las categorías y la descripción. Si incluiste datos técnicos, actualízalos y vuelve a enviar.",
            };
            if (response.status === 429) {
                const retry = Number(response.headers.get("Retry-After"));
                throw new Error(`Has hecho varios intentos. ${Number.isFinite(retry) && retry > 0
                    ? `Espera ${Math.min(Math.ceil(retry), 86400)} segundos` : "Espera unos minutos"} y vuelve a enviar. Tu borrador sigue aquí.`);
            }
            throw new Error(messages[response.status] || "No pudimos confirmar el envío. Vuelve a intentarlo sin cambiar el borrador.");
        }
        const receipt = await response.json();
        if (![200, 201].includes(response.status)
            || !/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(receipt.report_id)
            || typeof receipt.stored_at !== "string" || !Number.isFinite(Date.parse(receipt.stored_at))) {
            throw new Error("No pudimos confirmar el envío. Vuelve a intentarlo sin cambiar el borrador.");
        }
        return receipt;
    } catch (error) {
        if (controller.signal.aborted) throw new Error("La respuesta tardó demasiado. El reporte podría haberse guardado. Vuelve a intentarlo sin cambiar el borrador.");
        if (error instanceof TypeError) throw new Error("No pudimos conectar. Revisa tu conexión y vuelve a intentarlo. Tu borrador sigue aquí.");
        if (error instanceof SyntaxError) throw new Error("No pudimos confirmar el envío. Vuelve a intentarlo sin cambiar el borrador.");
        throw error;
    } finally {
        clearTimeout(timer);
    }
}
