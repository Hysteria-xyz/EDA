# El launcher y las novedades de EDA — qué cambiamos en las PR #77 y #78, y por qué

*Para el equipo de EDA (y su agente), de parte del dueño del launcher. 23-nov-2026.*

Antes de unirlas, editamos las PR #77 (versiones y NOVEDADES) y #78 (EDA en español). **No fue por no querer hacerlo
como ustedes lo planearon.** Las dos ideas eran buenas, y casi todo su trabajo quedó tal cual. Lo que cambiamos fue
**cómo llega eso al jugador**, porque el launcher ya tiene piezas hechas justo para eso. Usarlas da un resultado mejor
que sumarle algo aparte.

Acá está cada cambio, el motivo y cómo revisarlo. Si algo no les cierra, abran un issue o una PR y lo hablamos.

---

## 1. La versión del cliente: `AAAA.MM.DD.N`, sin letras

**Lo que proponían:** si sale más de una versión el mismo día, la segunda lleva una letra (`2026.11.22a`).

**Lo que cambiamos:** la segunda del día es **`2026.11.22.1`**, la tercera `.2`, y así.

**Por qué:** la nota de la PR suponía que el launcher compara con la biblioteca `semver` de Rust. No es así:
- valida la versión de EDA con `^[0-9]{1,8}(\.[0-9]{1,8}){0,7}$` (sólo números separados por puntos, hasta 8 partes);
- la compara número por número (`eda.rs`, `version_tupla`).

Con una letra, el launcher dice **«número de versión inválido» y nadie baja esa actualización**. Con `.1` entra y
queda mayor que la del día (`2026.11.22` < `2026.11.22.1` < `2026.11.23`).

**Dónde está:** commit `6286190` (PR #77).
- `herramientas/version_cliente.py`:
  - `VERSION` acepta `AAAA.MM.DD` y `AAAA.MM.DD.N` con N ≥ 1;
  - `revisar` rechaza la letra y el `.0`, y frena si la versión no pasa la validación del launcher;
  - las pruebas nuevas, con sus reveses: la letra → no; `.0` → no; `.1` mayor que sin número; la misma comparación
    que el launcher.
- `documentacion/VERSIONES.md`: la regla con el motivo.

`py herramientas\version_cliente.py control` → TODO BIEN.

---

## 2. Sin POP-UP: las novedades van en la PÁGINA DE EDA del launcher

**Lo que proponían:** un POP-UP que se abre solo, una vez, después de instalar una actualización. El texto salía de
una noticia que alguien tenía que cargar a mano en el panel.

**Lo que hicimos:** las novedades se ven siempre en la **pantalla de EDA del launcher** (desde el 3.0.31), en el
espacio que antes estaba vacío debajo del banner.

**Por qué:**
- **El launcher ya tiene contenido dinámico por juego** (la pantalla de R2Beat 2013 es el modelo), editable desde el
  **Coordinador**. EDA pasó a tener lo mismo: una «Página» propia que el staff de EDA edita (admin, o el moderador
  que tiene EDA), con permisos, auditoría y protección contra pisadas.
- **Un POP-UP se ve una vez y se pierde.** La página queda siempre a mano, con el historial de versiones.
- **No hay paso manual que olvidar:** el Coordinador importa sus entradas desde `NOVEDADES.json`.
- **Seguridad:** todo se muestra como texto plano (`textContent`), nunca como HTML.

**Cómo se ve:**

| bloque | sale de |
|---|---|
| **NOVEDADES** · versión · fecha · NUEVO | `version`, `fecha` (NUEVO hasta que el jugador lo mira) |
| la línea de resumen | `resumen` |
| **LO NUEVO** (a la izquierda) | `mejoras` |
| **CORREGIDO** (a la derecha) | `corregidos` |
| **IMPORTANTE** (franja abajo) | `avisos` |
| tu versión · versiones anteriores | la instalada y el historial publicado |

**Lo de ustedes que quedó igual (y es lo más importante):**
- **`NOVEDADES.json` es la fuente.**
- **`version_cliente.py revisar`** controla que esté completo y en texto plano antes de publicar.

El bloque `novedades` del manifiesto firmado (`version_cliente.py novedades`) sigue siendo opcional: el launcher
ignora los campos que no conoce, así que no rompe nada.

**El flujo:**
1. Cada PR que cambia lo que se reparte suma su entrada en `NOVEDADES.json` (con `"borrador": true`).
2. Al publicar la versión del cliente (con la orden de Rui), la entrada queda sin `"borrador"` y llega a `main`.
3. En el Coordinador → EDA → **Página**, «Importar de NOVEDADES.json» la trae como **borrador**, y «Publicar» la pone
   arriba, con NUEVO.

**Para escribirlas** (así quedan bien en la página):
- **frases cortas, para el jugador**, en español neutro (tú). El estilo que eligió el dueño:
  *«Conexión: problemas de P2P y Relay corregidos.»* · *«Opciones de calidad en Ajustes del juego.»*;
- **`mejoras`** = lo que se agregó; **`corregidos`** = lo que se arregló; **`avisos`** = lo que el jugador tiene que
  saber;
- **límites:** resumen 280, cada ítem 160, hasta 8 ítems por lista. Sin HTML ni direcciones de memoria.

**Dónde está:** commit `6286190` (sale `launcher/popup-novedades/`, y `VERSIONES.md` explica la página). Del lado del
launcher y del Coordinador, el código está en sus propios repos.

---

## 3. El idioma (PR #78): un selector en «Opciones del juego» de EDA

**Lo que trae la PR:** la traducción dentro de la DLL 0.5.4, prendida en español por omisión. Se cambia con
`[traduccion] idioma=` en `eda_d3d9.ini`.

**Lo que sumamos:** el jugador elige **Idioma** (Español / English) en el launcher, en Opciones del juego de EDA.
- El launcher escribe **sólo** `[traduccion] idioma=` en `eda_d3d9.ini`, con la misma rutina que ya usa para las demás
  opciones de EDA. Valida el valor (`^[a-z]{2,8}$`) y no toca el resto del archivo.
- **Los idiomas del selector salen de la Página de EDA del Coordinador.** Cuando sumen otro (por ejemplo `pt`), basta
  con agregar su carpeta en `traduccion/` y el idioma en el Coordinador: **no hace falta un launcher nuevo**.

**Por qué:** que el jugador no tenga que tocar archivos, y que si algo de la traducción falla pueda volver al inglés
con un clic.

**Dónde está:**
- commit `e51aa39` (PR #78): `traduccion/LEEME.md`, «Cómo apagarla o cambiar de idioma»;
- commit `80ad4b2`: trae la PR #77 al día.

No tocamos nada del código de la DLL ni de la traducción.

---

## 4. De paso: la DLL de `develop` no llegaba a la lista de prueba

Del 22 al 23-nov, la DLL que compila el CI en `develop` (release `cliente-develop`) **no llegaba a la lista del server
de prueba**.

**Por qué:** el armador de las listas del VPS (`eda_ensayo.sh`) corría en el mismo minuto que el actualizador de EDA
prod, con el mismo candado, y con `flock -n` se rendía siempre.

**El arreglo:** ahora corre 2 minutos después y espera el candado. El 23-nov 15:45 UTC la lista de prueba tomó la
DLL 0.5.4 (`b3ecd9f9`). Si notaron que «la DLL no se actualizaba en testserver», era esto.

---

## Cómo revisarlo

```
git show 6286190      # versión .N + sin POP-UP (PR #77)
git show 80ad4b2      # la #78 al día con la #77
git show e51aa39      # el selector de idioma, documentado (PR #78)
py herramientas\version_cliente.py control
```

**Estado al 23-nov:**
- `main` = `3be10c6` (#70 a #78).
- La Página de EDA está publicada con la versión que tienen hoy los jugadores (2026.11.21).
- Cuando salga la versión del cliente 2026.11.23 (la traducción), se importa y se publica desde el Coordinador.
