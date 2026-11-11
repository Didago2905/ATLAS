# Editorial V2.2 — edición rápida comercial (Phase 3B.2)

1. Confirmar una cerveza existente con `/carta22`.
2. Enviar `/rapido22` (mismos permisos beer.edit y autorización base existentes).
3. Elegir directamente entre los ocho campos comerciales y cinco precios.
4. Usar conservar, escribir mediante Reply, borrar opcionales, desconocido o
   descartar cambio. Tras responder se vuelve al selector/revisión; no se
   recorren los campos restantes. Atrás también vuelve al selector.
5. Revisar, editar otros campos y **Finalizar y conservar**. La recuperación
   con `/borradores22` preserva la modalidad rápida.

La revisión rápida muestra únicamente diferencias efectivas contra el baseline:
no incluye campos no elegidos, keep/unknown, sets idénticos ni clears de valores
ya ausentes. Sí distingue eliminar una clave de precio existente de conservarla,
incluso si su valor era null. Las intenciones originales siguen guardadas en el
patch: filtrar la vista no altera la propuesta ni sus revisiones.

**Ver resumen completo** / **Ver solo cambios** alternan la presentación sin
crear revisiones de contenido. `/resumen` sigue siendo de solo lectura y muestra
el resumen completo. Todos los botones de navegación mantienen los tokens de
caso/interacción/revisión y se invalidan después de las transiciones.

`/editar22` conserva su entrevista completa y secuencial. Ninguna entrada cambia
silenciosamente la modalidad de un caso comercial ya activo: retoma ese caso.
Para otro flujo, finalizar/conservar o cancelar primero, y confirmar la identidad
del nuevo caso. La edición rápida no crea cervezas ni cambia identidad confirmada.

Se reutilizan lector read-only, CommercialPatch, validadores, navegación,
ProposalRevision y el ciclo de borradores. `quick` y la presentación del resumen
son metadatos del contexto de entrevista; los contextos anteriores sin la marca
siguen el comportamiento completo. No hay cambios de esquema, migración, grants,
publicación, aprobación, activación Tap ni escrituras al catálogo/Museum.
