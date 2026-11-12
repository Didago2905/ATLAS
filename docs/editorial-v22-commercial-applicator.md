# Phase 3C.2 — aplicador transaccional interno, solo almacenamiento aislado

No hay ruta HTTP, comando Telegram ni carga automática de engine/configuración.
No se ha conectado atlas.db ni almacenamiento Editorial real durante desarrollo.
El prototipo rechaza atlas.db, archivos dentro del repositorio y raíces de prueba
que incluyan el repositorio. Ambos SQLite deben existir dentro de una raíz
aislada explícita, en archivos distintos. No está activable en producción tal cual.

## API y autorización

`apply_commercial_update(engine, editorial_database=..., isolated_root=...,
draft_id=..., case_id=..., revision=..., approval=..., authorization=...,
chat_id=..., user_id=...)` recibe un Engine SQLAlchemy explícito. Lee propuesta,
última revisión y contexto confiables desde la SQLite Editorial dentro de la
transacción, no de un payload suministrado por Telegram.

Requiere **beer.commercial.apply y beer.edit** mediante Authorization existente,
y propiedad del borrador por el mismo operador/grupo. beer.edit por sí solo no
autoriza. Solo se añadió el nombre de permiso al conjunto reconocido en código;
no se modificaron grants ni archivos runtime. No hay todavía aprobación delegada
de borradores ajenos.

CommercialApproval exige confirmación booleana true, UUID opaco de autorización,
caso, revisión exacta y request_sha256. `approval_digest(proposal, context)`
vincula el contrato completo y el hash del baseline validado. La validez técnica
o `prepared_for_review` no sustituyen esta confirmación. El borrador debe haber
sido finalizado/conservado; uno activo o cancelado no es aplicable.

Authorization y CommercialApproval son argumentos internos de confianza, no
credenciales firmadas para aceptar directamente de una red. Una futura interfaz
debe construirlos tras autenticar y autorizar al actor en servidor y vincular la
aprobación humana al digest exacto. El UUID no contiene IDs personales.

## Persistencia mínima y transacción

Es imprescindible una tabla nueva **en el catálogo de destino**:
`editorial_commercial_applications`. No sería atómico guardar el recibo solamente
en la base Editorial separada. Usa metadata SQLAlchemy independiente; no cambia
Base ni los arranques/migraciones existentes.

`initialize_receipts_for_isolated_tests(engine, isolated_root=...)` es el setup
aditivo explícito, idempotente y restringido a archivos de prueba. No hay CLI ni
migración real ejecutada. Se validan columnas, PK y unicidad caso/revisión.

1. Adjunta la fuente Editorial y ejecuta BEGIN IMMEDIATE en la conexión destino.
   Se necesitan handles con permiso de escritura para bloquear ambos SQLite;
   **solo se ejecutan SELECT contra la fuente Editorial**, nunca DML allí.
2. Revalida autorización tras obtener el lock; propietario, revisión/caso exactos,
   ausencia de revisiones posteriores, contexto conservado y digest aprobado.
3. Reutiliza la validación y cálculo de Phase 3C.1 sobre una lectura de la misma
   conexión/transacción, sin abrir una lectura externa. Comprueba identidad,
   baseline comercial completo, patches y valores actuales. Conflictos/no-ops
   se rechazan sin recibo ni update. Solo se admite una actualización existente.
4. Actualiza únicamente columnas comerciales con diferencias efectivas. Los
   precios se fusionan sobre el objeto leído, conservando claves no tocadas.
   No modifica disponibilidad, tap_position, borrado, destacados, imágenes ni
   relaciones de artwork/Museum; tampoco llama servicios con commits internos.
5. Inserta el recibo y hace **un commit conjunto de update y recibo**. Cualquier
   excepción revierte ambos. Libera locks y separa la fuente de la conexión.

La PK de aplicación es UUID5 determinista de caso/revisión, con otra restricción
única caso/revisión. BEGIN IMMEDIATE serializa escritores; dos solicitudes
idénticas devuelven un mismo recibo y solo una ejecuta el update. Dos propuestas
distintas compitiendo por el mismo baseline dejan una en conflicto.

El recibo incluye UUID de aplicación/caso/acción, revisión, beer_id, digest de
solicitud, referencia UUID de autorización, estado applied, UTC y diff por campo
con valores/presencias. No guarda IDs de actor/grupo ni contenido Telegram.
Es privado, sin endpoint público ni logging de payloads. Los timestamps propios
de Beer no se actualizan implícitamente mediante servicios ORM; el momento de
esta aplicación queda registrado en el recibo.

Un retry verifica otra vez permisos, propietario, integridad y revisión vigente,
y devuelve el recibo existente sin reaplicar ni comparar el baseline anterior
contra el SQL ya actualizado. Si el caso fue supersedido, se rechaza incluso
ese retry; el recibo histórico permanece. Un mismo identificador con contenido
distinto se rechaza. Fallos no se persisten como aplicaciones exitosas.

## Validación y pendientes

14 pruebas nuevas offline: precio único y varios campos, TEXT/JSON de precios,
campos operativos intactos, fuente intacta, stale/identidad, permisos y confirmación,
contenido alterado/supersedido, no-op/números inválidos, setup explícito, retries,
concurrencia idéntica y competitiva, revocación al adquirir el lock, bloqueo Editorial y rollback tras insertar
el recibo. Todos los archivos son temporales y Telegram es simulado.

Antes de producción: aprobar backup y migración real, diseñar la interfaz y
registro duradero de aprobación humana, resolver delegación, revisar privacidad/
retención del recibo, deshabilitar logs SQL con parámetros y probar modos de
journal, timeouts y contención del despliegue. BEGIN IMMEDIATE puede bloquear
brevemente otros escritores Editorial/catalog; un timeout falla de forma segura.
No eliminar el guard de aislamiento ni activar grants sin esa revisión separada.
