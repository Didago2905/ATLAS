# Phase 3C.1 — preparación comercial de solo lectura

API interna (sin endpoint ni integración Telegram):

```python
from app.editorial.commercial_preparation import prepare_commercial_update

result = prepare_commercial_update(
    database_url,
    proposal=proposal_payload,
    interview_context=active_history_or_saved_context,
)
```

El caller debe obtener propuesta y contexto de persistencia confiable y aplicar
su autorización. No aceptar esos argumentos directamente de un cliente como
prueba de identidad o aprobación. Para un caso conservado, usar su `context`
del archivo saved_cases, no el contexto de otro caso actualmente activo.

## Validación y resultado

- Admite exactamente una identidad ExistingBeer y una acción commercial_change
  referida a ella. Rechaza creación, acciones compuestas, artwork/vocabulary
  adicional, contratos inválidos y contextos de otro caso/revisión/modo.
- Reutiliza Proposal22, CommercialPatch, validate_patch, apply_commercial_patch,
  IdentitySnapshot y la validación de navegación. No convierte versiones.
- Verifica el baseline completo y su SHA-256 con el mismo JSON del inicio de
  entrevista; conserva grafía, claves de precio antiguas, cero y null.
- Lee una sola instantánea comercial mediante el lector existente: SQLite URI
  mode=ro, query_only y authorizer de SELECT limitado a beers. No importa el
  motor operativo, servicios con commit, configuración ni persistencia Editorial.
- Verifica ID, nombre, cervecería, estilo y fingerprint de confirmación. Si la
  referencia incluye origen, lo compara también. record_version no dispone de
  fuente SQL verificable: se rechaza en vez de inventar un valor.
- Compara todos los campos comerciales y todas las claves prices, no solamente
  los seleccionados. Cualquier drift bloquea como `conflict`, incluso si SQL ya
  coincide con el precio propuesto. No resuelve conflictos ni aplica last-write-wins.
- Los paths de diff son tuplas: (`prices`, `taster`) distingue claves reales
  de precio con puntos. Cada diff incluye presencia y valor antes/después:
  borrar una clave, tener null y fijar cero son casos distintos.
- `current` y `proposed` son copias privadas de los campos comerciales. La
  proyección fusiona cada precio sobre current sin perder claves no tocadas.
  `changes` contiene solo diferencias efectivas; `conflicts`, baseline → current.
  También conserva caso, revisión, acción, ID SQL, fingerprint y confirmación
  de identidad, además de hashes baseline/current. No cambia los originales.

Estados: `prepared` (diff sin conflictos), `noop` (sin cambios efectivos) o
`conflict`. **Todos tienen approval_required=True**. No son aprobación, publicación,
activación, transacción reservada ni comando ejecutable de escritura.

Entradas ambiguas/invalidas o fuente inaccesible generan PreparationError con
códigos fijos sin valores privados. No se registran snapshots ni diffs en logs.
Falta y eliminación se rechazan; un cambio de identidad válido marca conflicto.
Se exige JSON privado acotado a 64 KiB y precios numéricos finitos/no negativos;
no se corrigen silenciosamente datos fuente inválidos. Datos de resultado deben
permanecer privados aunque sus representaciones de debug omiten valores.

## Antes de habilitar escrituras

Los servicios actuales crean/actualizan con commits internos; update_beer puede
asignar/quitar tap_position y escribir featured.json según el payload, y prices
se sustituye como objeto. Esta capa no los llama. Tampoco toca imágenes,
disponibilidad, destacados, slots, Museum ni tablas Editorial.

Un aplicador futuro necesita autorización y aprobación explícitas vinculadas
al contenido/revisión, transacción atómica que relea/verifique la instantánea
antes del write, allowlist de campos y merge de precios, idempotencia, recibo de
aplicación y rollback controlado. La preparación cierra la conexión al terminar:
SQL puede cambiar después; nunca usar el resultado como permiso para aplicar
sin otra comprobación. Creación y Tap quedan fuera de este incremento.

Tests nuevos: diez pruebas offline con SQLite temporal, Telegram simulado y
comprobación de hashes/no nuevas revisiones. No se prepara ningún caso real.
