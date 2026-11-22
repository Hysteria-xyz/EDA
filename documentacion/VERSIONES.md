# Versiones del cliente y novedades (regla permanente, 21-nov-2026)

**Toda actualización que el launcher reparta a los jugadores lleva una versión nueva, sus novedades y su revisión.**
Se usa el sistema que ya funciona, sin inventar otro.

## Qué número es cuál
| qué | dónde vive | formato | quién lo sube |
|---|---|---|---|
| **Release del cliente** (lo que baja el launcher) | `version` de `eda.json` (`armar_cliente.py`), firmado con `firmar_manifiesto.py` | `AAAA.MM.DD` (o `AAAA.MM.DDa/b/c`) | quien publica |
| **DLL** | `herramientas/dll_d3d9/VERSION`, más el commit y el build dentro de la DLL (`EDA-ID\|v=…\|c=…\|s=…`) | `x.y.z` | la PR que cambia la DLL |
| **Server** (solo server) | el commit de despliegue (`/opt/eda/actualizaciones.log`) | commit | el CI y el cron del VPS |

- El launcher guarda la última release que aceptó (`eda_ver_ok` en `launcher.json`) y **rechaza** una menor. Por eso cada publicación tiene que subir la versión.
- Un cambio **solo del server** no genera descarga ni release del cliente.
- **TEST y prod van por separado:**
  - TEST: canal `cliente-develop` (CI) y manifiesto de *ensayo* (`R2_EDA_MANIFIESTO_PRUEBA`).
  - Prod: manifiesto firmado en el dominio de EDA, con la orden de Rui.

## El número de versión (regla del dueño, 22-nov-2026)
- La versión del cliente es **`AAAA.MM.DD`**: el día en que se publica.
- Si sale **más de una el mismo día**, se le agrega una letra minúscula: `AAAA.MM.DDa`, `AAAA.MM.DDb`, `AAAA.MM.DDc`…
  La **primera del día va sin letra**.
- Orden: `2026.11.21` < `2026.11.21a` < `2026.11.21b` < `2026.11.22`.
- Reemplaza a la regla vieja de cuatro números (`AAAA.MM.DD` y un `.1` al final), que **ya no vale**: `revisar` la rechaza, igual que una letra en mayúscula.

## La regla (la hace cumplir `py herramientas\version_cliente.py revisar`)
1. La versión nueva es `AAAA.MM.DD` (o con letra, si ya salió otra ese día) y **mayor** que la anterior.
2. Tiene su entrada en `NOVEDADES.json`, completa y sin `"borrador"`:
   - fecha y resumen;
   - al menos una de estas listas: corregidos, mejoras o avisos;
   - texto plano, sin HTML.
3. **Algo cambia.** Si no cambia ningún archivo, no se publica. Solo se bajan los archivos cuyo md5 cambió.
4. Si cambia `d3d9.dll`:
   - tiene la marca EDA-ID;
   - **no** es una compilación sucia;
   - es exactamente la del manifiesto (por md5: nada de archivos viejos);
   - su `VERSION` es **mayor** que la de la release anterior y coincide con `"dll"` de su entrada.
5. Si cambia `EDA_limpio.exe`, la revisión **se detiene**: su md5 es la clave del protocolo. Primero el server tiene que conocer la clave nueva.
6. `autoexec.cfg` y `eda_d3d9.ini` son del jugador: el launcher los baja solo si faltan.

## Publicar (con la orden de Rui)
1. Que la PR del cambio suba `herramientas/dll_d3d9/VERSION` (si cambia la DLL) y agregue su entrada a `NOVEDADES.json` (con `"borrador": true` mientras no se publica).
2. Compilar la DLL desde un clon limpio o tomar la del CI. **Nunca** la de una copia con cambios.
3. Armar y revisar:
   ```
   py herramientas\armar_cliente.py
   py herramientas\armar_cliente.py manifiesto AAAA.MM.DD BASE SERVIDOR CANJE
   py herramientas\version_cliente.py revisar _trabajo\eda.json ANTERIOR\eda.json --carpeta _trabajo\cliente_repartir
   ```
   Si dice ⛔, no se publica.
4. Quitar `"borrador"` y poner la fecha. Después:
   ```
   py herramientas\version_cliente.py novedades _trabajo\eda.json
   py herramientas\firmar_manifiesto.py firmar _trabajo\eda.json <privada> > manifiesto.jws
   ```
   Las novedades van **firmadas** junto con el resto.
5. Subir primero los archivos y **después** el manifiesto. Así nadie recibe un manifiesto que apunta a archivos que todavía no están.
6. Comprobar con `identificar.py` sobre una instalación hecha por el launcher: la DLL y la release tienen que ser las publicadas.

**Volver atrás:** no se puede servir una versión menor, porque el launcher la rechaza. Se publica **otra versión mayor** con los archivos anteriores y una entrada en NOVEDADES que lo explique. Por eso se guardan los archivos de cada release (`/opt/eda/files-eda/<release>-<azar>/`).

## El POP-UP de novedades (lo muestra el launcher de R2Beat)
El launcher es de R2Beat (repositorio aparte, Tauri). Ya tiene un panel de **Noticias** (`noticias.js`) con:
- noticias por juego y generales;
- etiqueta, fecha, imagen, «NUEVO» y fijadas;
- `noticias_vistas` guardadas en `launcher.json`.

Lo que se propone sumarle para las novedades de EDA, con su mismo estilo:
- **Dato:** el bloque `novedades` del manifiesto firmado: `{version, fecha, resumen, corregidos[], mejoras[], avisos[]}`.
- **Cuándo se muestra:** una vez por versión, **después** de que la actualización se bajó, se verificó (md5) y quedó instalada.
  - Si algo falla, no se marca ni se muestra.
  - Se guarda `eda_novedades_vistas: "<versión>"` en `launcher.json`.
  - Nunca mientras EDA está abierto: si está jugando, espera a que cierre.
- **Cómo se ve:**
  - arriba, «EDA» con la versión y la fecha;
  - el resumen en una línea;
  - después, en este orden: «Importante» (avisos, destacado), «Corregido» y «Mejoras»;
  - un solo botón, «Entendido»;
  - y la entrada queda en el panel de Noticias de EDA para volver a leerla.
- **Compatibilidad:** un launcher que no conoce `novedades` tiene que ignorar el campo. Hay que confirmarlo con R2Beat **antes** de publicar un manifiesto que lo traiga; mientras tanto, `version_cliente.py novedades` no se corre.

## Lo que cada entrega dice (plantilla)
```
Versión anterior: …        Versión nueva: …        (DLL: x.y.z → x.y.z')
Archivos modificados: …    (los demás no se vuelven a bajar)
Cambios visibles para los jugadores: …
Pruebas realizadas: … (automáticas / en el juego, entorno, fecha)
Texto del POP-UP: (py herramientas\version_cliente.py popup VERSIÓN)
Publicación: pasos 1–6 de arriba · Reversión: versión mayor con los archivos anteriores
```

## Borrador en curso: 2026.11.22 (dll 0.5.3) — qué pasó las pruebas

Estado: **borrador** (no publicado). El contenido final se decide por lo que pasa las pruebas, no por lo programado.
Base: develop **7823eca** (con #68, el selector de Stage = dll 0.5.1). La release lleva la dll **0.5.3** (`a9678cda`,
commit 04e141d): 0.5.1 (selector) + 0.5.2 (las llamadas sin resolver / mal resueltas) + 0.5.3 (el diagnóstico).

| Qué | Dónde | Resultado |
|---|---|---|
| La caída 0x7F4626 | EDA-PRUEBA-APIS, dll 0.5.1-candidata e2bf4df2 (21-nov 18:17–18:21) | ✅ se reproduce sin la reparación; con ella `setlocale("korean")` vuelve; 1 Stage sin errores |
| Pruebas sin juego | `prueba_apis.c/.py`, `prueba_selector.c`, `prueba_diag.c/.py`, `diag_partida control`, server | ✅ (CI) |
| El diagnóstico de punta a punta | EDA-PRUEBA-DIAG (server local, dll 0.5.3 a9678cda, 21-nov 19:15) | ✅ 7 lotes, 16 eventos, 0 fallos, el más lento 32 ms; el server los guardó y diag_partida los puso en su partida |
| FPS con y sin diagnóstico | EDA-PRUEBA-DIAG sin / con (1 Stage cada una, sin tope) | ✅ sin 148 (mín 66) · con 161 (mín 85): sin pérdida medible (la diferencia entre dos partidas es de ±10 %) |
| La caída 0x7F4626 con la dll final | EDA-PRUEBA-DIAG (las dos veces) | ✅ `setlocale("korean")` vuelve, sin errores |
| El POP-UP | `launcher/popup-novedades/probar_popup.js` con el Launcher.exe de TEST | ✅ 14/14 en la pantalla del launcher (falta el launcher recompilado por su dueño) |
| Partida de DOS en TEST | — | pendiente (después del despliegue autorizado) |

La versión ANTERIOR es **2026.11.21** (TEST, publicada el 21-nov ~19:00 con la dll 0.5.1 del selector: el launcher de la
PC de pruebas la bajó a las 19:02). Por eso las novedades de 2026.11.22 ya NO repiten el arreglo del selector.
⚠ **El formato, a confirmar con el dueño del launcher antes de publicar:** lo que el launcher ya aceptó tiene TRES números
(`2026.11.19`, `2026.11.21`). El launcher trae la biblioteca `semver` de Rust, que sólo acepta tres números sin ceros a
la izquierda. `2026.11.22` (tres números) entra igual que `2026.11.21`, sin aviso. Una versión **con letra**
(`2026.11.22a`, la segunda del mismo día) no es semver: hay que confirmar con el dueño del launcher que la acepta.
`revisar` lo avisa.
Si se publica otro día, la versión es la de ESE día: `AAAA.MM.DD` (o `AAAA.MM.DDa`, `AAAA.MM.DDb`… si ya salió una ese
día), siempre mayor que la anterior; `version_cliente.py revisar` lo exige.
