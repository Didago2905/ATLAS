# Editorial V2.2 — entrevista comercial (Phase 3B)

Solo propuestas: no escribe en el catálogo SQL ni en Museum, no publica,
aprueba, activa, asigna slots ni cambia destacados. No requiere migración.

## Campos y límites

Se inspeccionaron `app/models/beer.py`, `app/schemas/beer.py`, el contrato
Editorial y los cinco precios usados por el frontend. Campos cubiertos:
name, brewery, style, origin, color, description, abv, ibu; precios individuales
taster, pinta_chica, pinta_grande, jarra_chica, jarra_grande.

Nombre/cervecería: 1–255 caracteres; estilo: 1–100; origen: 1–255; color:
1–80; descripción: 1–800. ABV: 0–100; IBU: 0–2000; precios finitos:
0–1.000.000. Se reutilizan las restricciones Editorial existentes (más
acotadas que SQL Text/String sin límite en descripción/color). Los números
se introducen sin unidades ni separadores de miles; se admite coma decimal.
Se distingue precio cero de ausencia. Valores existentes no editados se
conservan, incluyendo otras claves antiguas del objeto prices.

Las URLs de imagen/fondo son activos, no campos de esta entrevista.
is_available, tap_position, is_featured, featured_updated_at, is_deleted,
IDs y timestamps no se editan. La nueva acción de propuesta `beer_create`
exige un NewBeer, sus valores deben coincidir con el patch y lleva
is_available=false. Es el campo SQL existente: no se añade una columna.
El default SQL actual es true, por lo que un futuro publicador deberá
respetar explícitamente este false; no existe publicador en este incremento.

## Flujo

- `/nueva22`: inicia un caso data-only si no existe otro activo. Requiere
  beer.create y la autorización base artwork.submit del bot existente.
- Para editar: `/carta22`, Reply con nombre, confirmación humana del candidato,
  después `/editar22`. Requiere beer.edit y la autorización base. Se vuelve a
  verificar la identidad y se lee una instantánea comercial estrictamente
  read-only usando la fuente catalog_database_url ya configurada.
- Cada campo ofrece conservar, escribir o indicar que falta información.
  Solo los opcionales ofrecen borrar. Escribir requiere Reply al prompt
  vigente; no se capturan mensajes espontáneos. Unknown no borra un valor.
- Conservar/unknown no descartan una intención de cambio anterior. Se indica
  «Conservar propuesta» cuando ya hay un cambio. «Descartar cambio; volver al
  original» retira explícitamente ese cambio y conserva el valor fuente.
- Atrás, `/corregir`, resumen y botones por campo permiten revisar y corregir.
  `/continuar` recupera la pregunta. `/resumen` es de solo lectura y no crea
  revisiones. El resumen abrevia textos, pero las propuestas guardan lo completo.
- Una propuesta incompleta se conserva sin inventar campos. Validación técnica
  no significa aprobación. No hay botón de publicación. `/cancelar` conserva
  revisiones y permite iniciar nuevamente V2.1 mediante sus comandos habituales.

## Persistencia y seguridad

Se reutilizan ProposalRevision e Interview.history, sin tablas nuevas.
Las acciones commercial_change y beer_create llevan CommercialPatch. Para
creación, ProposedBeer es su proyección validada, no otra entrada editable.
La identidad existente conserva snapshot, fingerprint y referencia a la
confirmación humana original. Baseline comercial y SHA-256 se guardan en el
estado privado de entrevista, máximo 64 KiB de JSON, nunca en logs. Sus valores
originales no se reemplazan durante correcciones o reinicios.

Los callbacks b22 están ligados a caso, interacción y revisión; los permisos
se vuelven a verificar antes de modificar. Navegar no crea revisiones de
contenido. Cancelar no borra las propuestas previas ni sus medios. Un caso
activo ajeno al flujo nunca se sustituye.

No se verifica continuamente el catálogo durante la entrevista. Antes de
cualquier publicación futura será obligatorio releerlo y comparar la identidad
y el baseline completo/digest dentro del procedimiento de concurrencia elegido.
Esta fase no concede permisos nuevos, cambia grants, configura el worker,
lo reinicia ni utiliza Telegram real durante tests. Los clientes antiguos no
conocen beer_create: no deben editar estas propuestas mediante un rollback.
