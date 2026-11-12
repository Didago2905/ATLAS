# Tap entry ordering: despliegue y recuperación

Documento de procedimiento. **No autoriza ejecutar ninguno de estos pasos.**
Usar PowerShell desde la raíz del repositorio para las comprobaciones; el panel
backend original es cmd.exe. No ejecutar terminal.bat ni crear otro supervisor.
Mantener Vite, Cloudflare y Operations existentes. No enviar comandos Telegram ni
aprobar propuestas durante el despliegue. Cada fallo detiene la secuencia.

## 1. Preflight de solo lectura

1. Registrar `git branch --show-current`, `git rev-parse HEAD`, `git status --short`
   y revisar `git diff --check`. Debe ser main con únicamente el cambio Tap aprobado.
   La referencia previa a este cambio es
   `80a02364ae62baec91c48afb80a68c129b5c2222`. Conservar una copia del diff y de los
   archivos nuevos fuera del árbol servido antes de cualquier rollback de código.
   No asumir que esos cambios ya están comprometidos en Git.
2. Registrar PID, padres, cuentas y hora de inicio de supervisor, FastAPI,
   Editorial e Incidents. Asociar el listener 8001 a su proceso. No confundir los
   wrappers del venv con workers adicionales ni uvicorn de otras aplicaciones.
3. Leer settings/permisos privados sin imprimir IDs ni credenciales. Confirmar
   destinos, UUID/not_before, capacidad comercial y grants existentes; no cambiarlos.
   Comprobar overrides en el terminal que se reutilizará; si no se puede resolver
   inequívocamente el destino, STOP.
4. Abrir el catálogo y Editorial mediante SQLite URI `mode=ro` y `query_only=ON`.
   En `editorial_interviews.history.execution_requests`, exigir cero pending,
   executing y failed retryable. Un resultado ambiguo requiere investigación,
   nunca ejecutar `/recuperar22` como parte del despliegue.
5. Registrar en privado rutas canónicas y `(st_dev, st_ino, st_nlink)`, esquema,
   integridad, claves foráneas y el Tap actual:

   ```sql
   SELECT id,name,tap_position,is_featured,is_available
   FROM beers
   WHERE is_deleted=0 AND is_available=1 AND tap_position IS NOT NULL
   ORDER BY tap_position,id;
   ```

   La referencia ensayada tiene 87 cervezas y 15 elegibles; su orden visual Tap es
   `14,16,79,80,61,74,57,15,17,10,18,25,78,2,12`. Si cambia, no continuar usando
   silenciosamente esa referencia. Registrar también `/api/public/tap` y el modo
   Tap del navegador. Las ordenaciones alternativas pueden mostrar otro orden.

## 2. Pausa y backup fresco — requiere autorización

Pedir al operador Ctrl+C en el panel backend original. Esperar salida normal de
supervisor, FastAPI, Editorial e Incidents. No matar procesos ni cerrar otros
paneles. Si no terminan normalmente, STOP. Confirmar ausencia de workers y puerto
8001 libre. Comprobar que ningún proceso mantiene abiertos ambos SQLite, por
ejemplo mediante Restart Manager o este probe exclusivo **sin escritura**:

```powershell
$repo = (Get-Location).Path
$catalog = Join-Path $repo 'atlas.db'
$editorial = Join-Path $repo 'data\editorial\storage\editorial.sqlite3'
foreach ($path in @($catalog, $editorial)) {
    $handle = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    $handle.Dispose()
}
```

Crear un directorio NUEVO timestamped bajo el hermano `ATLAS_BACKUPS`, fuera del
repositorio. Con autorización de ACL limitada a ese directorio, quitar herencia y
permitir solo operador, SYSTEM y Administradores; verificar antes de copiar. No
alterar ACL padre ni fuentes. No sobrescribir backups ni reutilizar el rehearsal.

Con `$backupDir` apuntando a ese directorio privado y nuevo:

```powershell
.\.venv\Scripts\python.exe -B -m app.editorial.storage --source-database $editorial --source-media (Join-Path $repo 'data\editorial\storage\media') --destination (Join-Path $backupDir 'editorial')
if ($LASTEXITCODE -ne 0) { throw 'STOP: backup Editorial no verificado' }
```

Ese CLI existe, exige worker/lock libre y verifica SQLite, registros y medios.
Para el catálogo usar online backup, NO una copia de atlas.db con Copy-Item:

```powershell
@'
from contextlib import closing
from pathlib import Path
import sqlite3,sys
source=Path('atlas.db').resolve(strict=True)
target=Path(sys.argv[1])/'catalog.sqlite3'
assert not target.exists()
with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as db:
    db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
    with closing(sqlite3.connect(target)) as backup:db.backup(backup)
'@ | .\.venv\Scripts\python.exe -B - $backupDir
if ($LASTEXITCODE -ne 0) { throw 'STOP: backup catálogo fallido' }
```

Antes de migrar, verificar ambos backups con conexiones ro: integrity_check=ok,
foreign_key_check vacío y esquema/valores completos iguales a las fuentes, no solo
counts. Verificar originales y previews contra el recibo Editorial. Crear manifiesto
privado con paths, identidades, tamaños, SHA-256 de todos los archivos, counts,
orden Tap, resultados y requisitos de restauración; guardar y revalidar su hash.
El backup y su manifiesto se conservan inmutables. Si no se dispone de estas
verificaciones, STOP. Una copia creada sin verificarlas no habilita el siguiente paso.

## 3. Migración explícita — segundo checkpoint de autorización

Reconfirmar servicios/handles cerrados, backup íntegro e identidades sin cambios.
El único CLI de migración soportado es:

```powershell
.\.venv\Scripts\python.exe -B -m app.migrations.tap_entry --database .\atlas.db
if ($LASTEXITCODE -ne 0) { throw 'STOP: investigar migración, no reiniciar' }
```

No tiene `--create`, `--upgrade` ni `--rollback`. No importa app.main y no migra
Editorial. Añade exclusivamente `tap_entered_at DATETIME`, nullable, sin default ni
backfill, dentro de BEGIN IMMEDIATE. Repetir valida la columna y no cambia nada;
no repetir después de un fallo sin investigar primero.

Antes de arrancar exigir:

- PRAGMA table_info: columna nueva DATETIME, notnull=0, default NULL, no PK.
- Los 87 timestamps son NULL y los 87 registros originales coinciden campo por
  campo con el backup, excluyendo únicamente la columna nueva.
- Todos los demás esquemas, índices y valores permanecen iguales: incluidos
  issue_reports y los recibos comerciales existentes.
- Integridad ok, claves foráneas sin infracciones, mismas identidades físicas.
- El Tap conserva IDs, posiciones, disponibilidad y destacados y el orden legacy.
- Bases/medios Editorial y manifiesto de backup intactos.

Registrar resultados. Si alguna comprobación falla, permanecer detenido.

## 4. Arranque único y verificación — requiere autorización

No reiniciar antes de completar la migración: el nuevo ORM falla si falta la
columna y create_all NO altera una tabla existente. En el panel backend original,
desde la raíz, comprobar overrides y ejecutar **una sola vez**:

```bat
.\.venv\Scripts\python.exe -B -m app.dev_launcher
```

Confirmar una instancia lógica de FastAPI, Editorial e Incidents bajo el supervisor
y la cuenta esperada, HTTP 200 en `http://127.0.0.1:8001/`, sin reinicios ni errores
de schema/configuración. Corroborar archivos reales abiertos y sus identidades.
La tabla de recibos debe validar y conservar sus filas; ningún request o aplicación
nuevo debe aparecer. La capacidad comercial/grants conservan su estado anterior;
no probar salud aplicando precios ni recuperando solicitudes.

Comparar `http://127.0.0.1:8001/public/tap` y
`http://127.0.0.1:5173/api/public/tap`: mismos IDs/valores, ahora timestamp null.
SQL/API siguen ordenando por posición; la prioridad featured ocurre en frontend.

El launcher actual usa Vite dev en 5173 y Cloudflare apunta a 5173: el comparator
se sirve desde fuente mediante Vite/HMR, sin copiar dist ni reiniciar el túnel.
Recargar el navegador, seleccionar modo Tap y reabrir BeerDetail para descartar
snapshots de navegación. Verificar las 15 cervezas y un hueco final, y comprobar
Nombre/Estilo/Alcohol sin cambiar sus reglas.

El build ya es un control de calidad; no es el artefacto servido por este launcher.
Si otro despliegue sirve estáticos, requiere `npm run build` desde frontend y la
publicación aprobada de su outDir real. No asumir que dist/build temporales se
publican solos ni reemplazar el build servido durante este procedimiento.

## 5. Recuperación: detenerse, preservar evidencia, pedir autorización

| Situación | Acción segura |
|---|---|
| Migración falla | Mantener backend parado; comprobar esquema, integridad y datos ro. El migrador intenta rollback transaccional. Si sigue el esquema anterior intacto, se puede volver al código anterior con aprobación. No reintentar ni restaurar automáticamente. |
| Arranque falla tras migrar correctamente | No abrir otro supervisor. Si quedó un proceso activo, pedir su cierre normal y verificar hijos/locks. Conservar columna y datos; investigar logs o autorizar rollback de código. |
| Orden visual inesperado | No reordenar SQL ni inventar timestamps. Revisar modo guardado, datos API frescos, comparator servido, featured y snapshot de navegador. Pausar operaciones Tap; autorizar rollback de frontend si se confirma regresión. |
| Datos inesperadamente distintos | Suspender operaciones, cerrar backend de forma controlada con autorización y conservar una copia diagnóstica antes de cualquier reparación. Comparar con backup; no restaurar mientras existan conexiones ni sobrescribir datos posteriores sin decisión explícita. |

Volver al código previo es compatible con conservar la columna nullable: el ORM
anterior la ignora y el esquema previo no debe recrearse. Antes, guardar el cambio
actual para no perder trabajo. Con autorización de recuperación, los archivos
runtime a recuperar desde la referencia previa son `app/models/beer.py`,
`app/schemas/beer.py`, `app/services/beer_service.py` y
`frontend/src/components/TapGrid.jsx`. No restablecer todo el repositorio ni tocar
settings, grants o recibos. Reiniciar solo cuando todas las comprobaciones pasen.
Mientras opere código anterior no hacer entradas/reactivaciones para validar la
nueva política: ese código no mantiene tap_entered_at.

La restauración SQLite es un último recurso separado: autorización específica,
todos los usuarios detenidos, backup/hash/medios verificados, preservar el estado
actual, manejar sidecars offline y restaurar el conjunto correcto. Una sustitución
de archivo exige revisar la identidad física y allowlist comercial antes de arrancar.
No dar por válido el backup de antes de la primera aplicación comercial para este
despliegue: usar el backup FRESCO de la sección 2.

**PROHIBIDO restaurar catalog-rehearsal.sqlite3:** contiene activaciones de prueba.
Ni esa copia ni sus timestamps sintéticos son una fuente de producción. El backup
prístino del ensayo es evidencia, no sustituto del backup fresco autorizado.

Este runbook no ejecuta restauraciones, cambios de configuración, permisos,
migraciones, arranques ni operaciones comerciales.
