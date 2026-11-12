# Phase 3C.3 — revisión y autorización autenticadas; ejecución deshabilitada

## Alcance deliberado

Se implementa la alternativa UI-only permitida en esta fase. EditorialService
procesa su inbox bajo BEGIN IMMEDIATE en la base Editorial. El aplicador 3C.2
necesita otra conexión y BEGIN IMMEDIATE sobre catálogo y esa misma fuente;
llamarlo directamente desde el manejador causaría contención/autobloqueo y no
resolvería la recuperación tras resultados ambiguos. Hace falta una etapa de
ejecución posterior al commit, con persistencia/reconciliación propias.

Por eso **no hay llamada al aplicador desde Telegram**, ni flag, variable de
entorno, configuración o callback que active escrituras SQL. Sigue intacto su
guard de almacenamiento aislado. Tampoco se ejecuta el setup de recibos ni se
modifica runtime permissions, catálogo, Tap, Museum, propuestas o revisiones.
La UI persiste únicamente metadatos privados de revisión/autorización mediante
Interview.history y usa el inbox/outbox existentes.

## Flujo

1. Finalizar y conservar una propuesta de actualización de cerveza existente.
   No debe haber otra entrevista activa. Creación no forma parte de este flujo.
2. `/aplicar22` muestra hasta diez actualizaciones propias conservadas más
   recientes, dentro del grupo autorizado. Seleccionar **Revisar** no autoriza.
3. La preparación 3C.1 consulta SQLite en modo estrictamente read-only y muestra
   valores exactos antes/después por path, con presencia/ausencia de claves.
   Si hay conflictos, muestra baseline → SQL actual y no ofrece confirmación.
   No-ops tampoco se autorizan.
4. Valores largos no se truncan: el diff se divide en páginas de como máximo
   1400 caracteres, avanzando secuencialmente. Confirmar solo se ofrece después
   de la última página. El encabezado identifica caso, revisión y cerveza SQL.
5. **Confirmar autorización** requiere otra interacción. Vuelve a cargar la
   propuesta/revisión vigente y a preparar contra SQL. Un cambio invalida o
   bloquea la revisión. El resultado válido es explícitamente «autorización
   registrada; ejecución SQL deshabilitada», nunca «aplicado».
6. `/recibo22` consulta en solo lectura un recibo existente para la última
   autorización. Solo muestra éxito cuando existe un recibo applied cuyo caso,
   revisión, cerveza, digest y referencia de autorización coinciden. Si falta
   tabla/recibo o no se puede verificar, no afirma ninguna aplicación.

## Vinculación y permisos

Se reutiliza el actor proyectado desde getUpdates, propiedad Draft por grupo/
operador, autorización base artwork.submit y permisos beer.edit **más**
beer.commercial.apply. Se comprueban tanto al listar/revisar como al confirmar
y consultar recibos; no se concedió ningún permiso real.

Cada revisión tiene nonce UUID nuevo y está vinculada a actor/grupo, UUID de
caso, revisión exacta, SQL beer_id, digest del contrato completo y baseline,
hash del snapshot SQL revisado y binding del archivo catálogo canónico.
La confirmación no acepta valores ni aprobación suministrados por un callback:
solo su nonce. El servidor reconstruye CommercialApproval tras revalidar todo.
Se conserva la referencia UUID opaca de aprobación, sin cambiar readiness ni
confundir validez técnica con autorización. Confirmaciones duplicadas no crean
otra referencia ni efectos SQL. Revisar de nuevo invalida el nonce anterior.

Los metadatos contienen IDs de actor en almacenamiento Editorial privado para
vincular la sesión; nunca se imprimen ni se incluyen en logs/recibos visibles.
Los diffs y sus páginas también permanecen privados. El recibo visible muestra
identificador de aplicación, cerveza, revisión, estado y timestamp persistidos,
sin cuerpos de mensajes, tokens ni IDs Telegram.

## Pruebas y siguiente paso

Nueve tests nuevos con Telegram simulado y SQLite temporal cubren permisos,
actor ajeno, autorización válida sin ejecución, nonce obsoleto, contenido
modificado, conflicto SQL posterior, duplicado, recibo persistido real, target
temporal llamado atlas.db sin escrituras y diff largo sin truncamiento.
Para probar recibos se invoca el aplicador 3C.2 como paso separado del fixture,
después de cerrar la transacción UI y únicamente sobre archivos temporales.

Pendiente: etapa/outbox de ejecución aislada fuera de la transacción UI, enlace
duradero y recuperación entre autorización y recibo, caducidad/administración de
autorizaciones y navegación de listas mayores. Hay una revisión pendiente por
operador: iniciar otra la sustituye e invalida sus botones; los recibos SQL
históricos no se borran. Antes de un rollout real se requieren backup/migración
aprobados, política de permisos/retención, pruebas de contención y autorización
explícita para cualquier cambio de los guards de producción. No activar todavía.
