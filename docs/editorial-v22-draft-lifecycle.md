# Editorial V2.2 — conservación y recuperación comercial (Phase 3B.1)

En la revisión comercial, **Finalizar y conservar** deja la propuesta como
borrador no aprobado y libera el contexto activo. No cambia sus campos,
readiness, case_id ni revisiones; tampoco publica, activa ni escribe en el
catálogo/Museum. Se admite conservar propuestas incompletas. El estado
Editorial pasa a `saved`; las propuestas y medios nunca se borran.

`/borradores22` lista los casos comerciales conservados del mismo operador
y grupo, con botones **Reabrir** y paginación de diez casos. Se aplican los
permisos existentes beer.create/beer.edit y la autorización base del bot.
No se conceden permisos nuevos. Reabrir se rechaza si hay otro contexto
activo, aunque sea V2.1; hay que finalizarlo o cancelarlo primero.

La reapertura conserva identidad, valores, baseline/digest y revisiones.
Devuelve la revisión comercial, sin reutilizar prompts de texto antiguos,
e invalida botones mediante una nueva interacción de navegación. No añade
una revisión de contenido hasta que haya una edición real. La revisión
nueva se asigna por encima del máximo del registro de borrador, aunque se
edite un caso antiguo. No se renumeran ni reescriben las filas anteriores.
Una lista con revisión antigua requiere actualizarse con `/borradores22`.

## Persistencia y compatibilidad

Se conserva la unicidad existente de Draft por grupo/operador. Interview.history
incluye `saved_cases`, un mapa por case_id con contexto comercial y navegación,
referenciando ProposalRevision por caso. No se añaden tablas ni migraciones.
Se reutilizan los snapshots inmutables; no se duplica la propuesta completa
en el archivo de contextos. Los contextos se conservan al iniciar otra Carta.

Para no perderlos al volver a V2.1, sus arrays de navegación siguen siendo
arrays cuando no hay archivo. Cuando existe, se guardan como `steps` dentro
de un envelope `legacy_with_saved`; los mismos pasos/transiciones V2.1 leen
y actualizan ese array, preservando el archivo comercial. Las formas de
historia desconocidas siguen rechazándose.

`/cancelar` conserva su significado anterior. En entrevistas comerciales,
también conserva el contexto recuperable con estado `cancelled`. Los comandos
V2.1 permiten iniciar su flujo posteriormente, sin asignarle las imágenes de
casos anteriores. La retirada de teclados es best effort; la autorización y
validación de callbacks siguen siendo obligatorias.

## Límites

- La lista cubre contextos comerciales conservados/cancelados mediante esta
  versión. Un caso actual de Phase 3B puede finalizarse sin conversión previa.
- Las revisiones antiguas cuyos contextos ya fueron sustituidos antes de esta
  funcionalidad no se borran, pero no se reconstruyen automáticamente: podría
  faltar su baseline/progreso original. Tampoco se archivan entrevistas V2.1
  ni casos Carta de solo identidad mediante esta lista.
- El mapa de contextos crece en el JSON privado del operador. La lista pagina
  sus resultados; no es un sistema de archivo masivo ni incluye eliminación.
- Recuperar no vuelve a consultar el catálogo; una futura publicación debe
  comprobar nuevamente identidad y baseline. Esta fase no publica ni aprueba.

Todo se prueba con SQLite y medios temporales y Telegram simulado. No se
migra almacenamiento real, reinician servicios ni cambian permisos.
