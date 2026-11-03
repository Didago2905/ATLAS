import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { collectIssueSnapshot } from "../diagnostics/issueSnapshot";
import { createReportKey, submitIssueReport } from "../api/issueReports";
import "./IssueReporter.css";

const CATEGORIES = ["Tap List", "Museo", "Información de cerveza", "Interacción / visualización", "Otro"];
const CATEGORY_LABELS = { "Información de cerveza": "Información de una cerveza", "Interacción / visualización": "Uso o apariencia" };
const MAX_BYTES = 5 * 1024 * 1024;

export default function IssueReporter({ open, onClose, triggerRef }) {
    const dialogRef = useRef(null);
    const closeRef = useRef(null);
    const receiptRef = useRef(null);
    const backdropPress = useRef(false);
    const attachmentSequence = useRef(0);
    const attemptRef = useRef(null);
    const submittingRef = useRef(false);
    const id = useId();
    const [categories, setCategories] = useState([]);
    const [description, setDescription] = useState("");
    const [attachment, setAttachment] = useState(null);
    const [attachmentError, setAttachmentError] = useState("");
    const [snapshot, setSnapshot] = useState(null);
    const [previewOpen, setPreviewOpen] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [submissionError, setSubmissionError] = useState("");
    const [receipt, setReceipt] = useState(null);
    // Match the server's Unicode character count rather than UTF-16 code units.
    const length = Array.from(description.trim()).length;
    const valid = categories.length > 0 && length >= 20 && length <= 2000
        && !attachmentError && (!attachment || attachment.valid);

    useEffect(() => {
        if (!open) return;
        const dialog = dialogRef.current;
        const trigger = triggerRef.current;
        dialog.showModal();
        closeRef.current.focus({ preventScroll: true });
        const updateViewport = () => {
            const visual = window.visualViewport;
            dialog.style.setProperty("--report-top", `${visual?.offsetTop || 0}px`);
            dialog.style.setProperty("--report-height", `${visual?.height || window.innerHeight}px`);
        };
        updateViewport();
        window.addEventListener("resize", updateViewport);
        window.visualViewport?.addEventListener("resize", updateViewport);
        window.visualViewport?.addEventListener("scroll", updateViewport);
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => {
            dialog.close();
            document.body.style.overflow = previousOverflow;
            window.removeEventListener("resize", updateViewport);
            window.visualViewport?.removeEventListener("resize", updateViewport);
            window.visualViewport?.removeEventListener("scroll", updateViewport);
            trigger?.focus({ preventScroll: true });
        };
    }, [open, triggerRef]);

    useEffect(() => {
        if (open && receipt) receiptRef.current?.focus({ preventScroll: true });
    }, [open, receipt]);

    const attachmentUrl = attachment?.url;
    useEffect(() => () => {
        if (attachmentUrl) URL.revokeObjectURL(attachmentUrl);
    }, [attachmentUrl]);

    function selectScreenshot(event) {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (!file) return;
        const sequence = ++attachmentSequence.current;
        setAttachment(null);
        setAttachmentError("");
        if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > MAX_BYTES) {
            setAttachmentError("Elige una imagen JPG, PNG o WebP de hasta 5 MiB.");
            return;
        }
        const url = URL.createObjectURL(file);
        const candidate = { file, url, valid: false };
        setAttachment(candidate);
        const image = new Image();
        image.onload = () => {
            if (sequence !== attachmentSequence.current) return;
            const accepted = image.naturalWidth > 0 && image.naturalHeight > 0
                && Math.max(image.naturalWidth, image.naturalHeight) <= 16_384
                && image.naturalWidth * image.naturalHeight <= 20_000_000;
            setAttachment(current => current?.url === url ? { ...current, valid: accepted } : current);
            // Ignore results belonging to a replaced/removed attachment.
            if (!accepted) setAttachmentError("Reduce la imagen: máximo 20 megapíxeles y 16 384 píxeles por lado.");
        };
        image.onerror = () => {
            if (sequence !== attachmentSequence.current) return;
            setAttachment(current => current?.url === url ? { ...current, valid: false } : current);
            setAttachmentError("No pudimos abrir la imagen. Elige otra captura.");
        };
        image.src = url;
    }

    async function handleSubmit(event) {
        event.preventDefault();
        if (!valid || submittingRef.current || receipt) return;
        submittingRef.current = true;
        setSubmitting(true);
        setSubmissionError("");
        try {
            const report = {
                schema_version: 1, categories: [...categories].sort(), description: description.trim(),
                diagnostic_consent: snapshot !== null,
                ...(snapshot !== null ? { diagnostics: snapshot } : {}),
            };
            const serialized = JSON.stringify(report);
            const file = attachment?.file || null;
            // A retry of unchanged content uses the original key, including after
            // a timeout where the server may already have committed the report.
            if (!attemptRef.current || attemptRef.current.serialized !== serialized || attemptRef.current.file !== file) {
                attemptRef.current = { key: createReportKey(), serialized, file };
            }
            const result = await submitIssueReport(report, file, attemptRef.current.key);
            setReceipt(result);
        } catch (error) {
            setSubmissionError(error.message || "No pudimos enviar el reporte. Tu borrador sigue aquí; vuelve a intentarlo.");
        } finally {
            submittingRef.current = false;
            setSubmitting(false);
        }
    }

    function startNewReport() {
        setReceipt(null);
        setCategories([]);
        setDescription("");
        attachmentSequence.current++;
        setAttachment(null);
        setAttachmentError("");
        setSnapshot(null);
        setPreviewOpen(false);
        setSubmissionError("");
        attemptRef.current = null;
        closeRef.current?.focus({ preventScroll: true });
    }

    return createPortal(
        <dialog ref={dialogRef} className="issue-reporter" aria-labelledby={`${id}-title`}
            aria-describedby={`${id}-notice`} onCancel={event => { event.preventDefault(); onClose(); }}
            onPointerDown={event => { backdropPress.current = event.target === event.currentTarget; }}
            onClick={event => {
                if (backdropPress.current && event.target === event.currentTarget) onClose();
                backdropPress.current = false;
            }}>
            <div className="issue-reporter__panel">
                <header className="issue-reporter__header">
                    <h2 id={`${id}-title`}>Reportar un problema</h2>
                    <button ref={closeRef} type="button" onClick={onClose} aria-label="Cerrar reporte">Cerrar</button>
                </header>
                <p id={`${id}-notice`}>Cuéntanos qué ocurrió para ayudarnos a mejorar ATLAS. Evita incluir información personal.</p>
                <p>Tu reporte se guarda de forma privada. El equipo de mantenimiento puede recibir un resumen.</p>
                {receipt ? <div>
                    <p ref={receiptRef} tabIndex={-1} role="status">Reporte guardado. ID: <strong>{receipt.report_id}</strong></p>
                    <button type="button" onClick={startNewReport}>Enviar otro reporte</button>
                </div> : <form onSubmit={handleSubmit} aria-busy={submitting}>
                    <fieldset disabled={submitting} className="issue-reporter__fields">
                    <fieldset>
                        <legend>¿Con qué tienes problemas? Elige una o más opciones.</legend>
                        {CATEGORIES.map(category => <label className="issue-reporter__choice" key={category}>
                            <input type="checkbox" checked={categories.includes(category)} onChange={event => {
                                setCategories(current => event.target.checked ? [...current, category] : current.filter(item => item !== category));
                            }} />{CATEGORY_LABELS[category] || category}
                        </label>)}
                    </fieldset>
                    {categories.length > 0 && <div>
                        <label htmlFor={`${id}-description`}>¿Qué pasó? (obligatorio)</label>
                        <p id={`${id}-help`}>Cuéntanos qué pasó y qué esperabas. Entre 20 y 2000 caracteres.</p>
                        <textarea id={`${id}-description`} rows={5} value={description} required
                            aria-describedby={`${id}-help ${id}-count`}
                            aria-invalid={description.length > 0 && (length < 20 || length > 2000)}
                            onChange={event => setDescription(event.target.value)} />
                        <p id={`${id}-count`}>{length} de 2000 caracteres</p>
                    </div>}
                    <label htmlFor={`${id}-screenshot`}>Captura de pantalla (opcional)</label>
                    <p>La captura se guarda de forma privada y no se envía por Telegram. Oculta cualquier dato personal.</p>
                    <p>JPG, PNG o WebP. Máximo 5 MiB y 20 megapíxeles.</p>
                    <input id={`${id}-screenshot`} type="file" accept="image/jpeg,image/png,image/webp" onChange={selectScreenshot} />
                    {attachment && <div>
                        <img className="issue-reporter__preview" src={attachment.url} alt="Captura seleccionada" />
                    </div>}
                    {(attachment || attachmentError) && <button type="button" onClick={() => {
                        attachmentSequence.current++;
                        setAttachment(null); setAttachmentError("");
                    }}>Quitar captura</button>}
                    <p role="alert" data-attachment-error>{attachmentError}</p>
                    <label className="issue-reporter__choice">
                        <input type="checkbox" checked={snapshot !== null} onChange={event => {
                            setSnapshot(event.target.checked ? collectIssueSnapshot() : null);
                            setPreviewOpen(false);
                        }} />Autorizo incluir datos técnicos (opcional)
                    </label>
                    <p>Incluye información sobre tu navegador, pantalla y conexión. No incluye contraseñas ni contenido de formularios. El equipo puede recibir un resumen.</p>
                    {snapshot && <section aria-label="Datos técnicos que enviarás">
                        <button type="button" aria-expanded={previewOpen} aria-controls={`${id}-snapshot`}
                            onClick={() => setPreviewOpen(current => !current)}>
                            {previewOpen ? "Ocultar datos técnicos" : "Ver datos técnicos"}
                        </button>
                        <div id={`${id}-snapshot`} hidden={!previewOpen}>
                            <h3>Datos que enviarás</h3>
                            <p>Navegador y sistema son aproximados. «null» significa que el dato no está disponible.</p>
                            <pre>{JSON.stringify(snapshot, null, 2)}</pre>
                            <button type="button" onClick={() => setSnapshot(collectIssueSnapshot())}>Actualizar datos</button>
                        </div>
                    </section>}
                    </fieldset>
                    <p role="alert" data-submission-error>{submissionError}</p>
                    <p role="status" aria-live="polite">{submitting ? "Enviando reporte…"
                        : attachmentError
                        ? "Cambia o quita la captura para continuar."
                        : attachment && !attachment.valid ? "Revisando captura…"
                        : valid
                        ? "Listo para enviar."
                        : "Elige al menos una categoría y escribe entre 20 y 2000 caracteres."}</p>
                    <button type="submit" disabled={!valid || submitting} aria-describedby={`${id}-notice`}>{submitting ? "Enviando…" : "Enviar reporte"}</button>
                    <p>Puedes cerrar y volver al borrador. Se pierde al recargar o salir de esta página.</p>
                </form>}
            </div>
        </dialog>, document.body,
    );
}
