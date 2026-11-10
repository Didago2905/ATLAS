# Consola operativa de bots

El acceso de inicio de sesión conserva `devtools/launcher/terminal.bat`.
Sus paneles originales de backend, Vite y Cloudflare no cambian. Una pestaña
adicional contiene tres lectores: Notifications, Incidents y Editorial.
`app.bot_console` solo lee logs: no inicia bots, importa credenciales ni
consume actualizaciones de Telegram. Cerrar un lector no detiene el worker.

## Logs

Directorio: `D:\Apps\Tuburon\ATLAS\devtools\runtime\bot-logs\`.
Archivos: `notifications.log`, `incidents.log`, `editorial.log`.
Cada archivo rota a 512 KiB, conservando tres copias (`.1` a `.3`):
aproximadamente 2 MiB por canal, 6 MiB en total. Quedan excluidos por Git.

Solo se admiten eventos enumerados de ciclo de vida, operación correcta,
fallo, transporte no disponible y entrega incierta. El handler rechaza
mensajes arbitrarios y elimina trazas de excepción. No hay textos de
Telegram, propuestas, IDs, capturas, URLs, credenciales ni payloads.
No cambia la entrega, el cursor, los reintentos ni la supervisión.
Errores al escribir logs no interrumpen los bots.

Los lectores esperan si aún no existe el archivo, leen en bloques acotados
y cierran el archivo entre lecturas para no impedir la rotación en Windows.
Muestran el archivo activo, no reproducen todas las copias rotadas. Los logs
son históricos: no son un heartbeat ni una prueba de salud actual. Una muerte
forzada puede no producir `stopped`; no se cambia el supervisor para detectarla.

## Activación y validación manual (no ejecutadas)

En el siguiente arranque normal autorizado, usar el launcher habitual solo
después de verificar que la sesión anterior terminó; no abrir otra instancia
encima de una sesión activa. Deben conservarse los tres paneles originales y
aparecer una pestaña adicional de tres lectores. No hay otro supervisor.

Para abrir únicamente un lector en una consola existente, desde el repositorio:

```powershell
.\.venv\Scripts\python.exe -B -m app.bot_console editorial
```

Se puede sustituir `editorial` por `incidents` o `notifications`. Esto no
recarga código de workers ya ejecutándose. La nueva instrumentación entrará
en vigor cuando cada proceso existente sea reiniciado de forma autorizada.
No provocar envíos reales solo para verificar los paneles.

Comprobar manualmente que hay un solo supervisor y los mismos consumidores,
que cerrar un lector no los detiene y que las líneas no muestran datos
privados. La distribución gráfica de Windows Terminal requiere esta
validación; las comprobaciones automáticas son estáticas y simuladas.

Validación de implementación: 79 tests offline aprobados (incluyen seis nuevos
de observabilidad), comprobación estática de comandos/continuaciones del BAT
y sintaxis Python, `git diff --check` correcto y acceso directo existente
verificado en modo lectura. Ningún proceso real fue iniciado o detenido.

## Rollback

Cerrar solo la pestaña de lectores. Para omitirla en el siguiente inicio,
retirar únicamente los tres comandos `app.bot_console` del BAT y el `^` que
los precede, preservando los comandos originales. El logging puede permanecer
sin lectores. Un rollback completo debe revertir solo el parche de esta
consola después de la parada autorizada correspondiente; no restaurar archivos
enteros que contengan trabajo Editorial anterior. No borrar datos Editorial.
