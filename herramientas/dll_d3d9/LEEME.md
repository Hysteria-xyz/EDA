# herramientas/dll_d3d9 — el `d3d9.dll` propio de EDA

Va **al lado del juego**: la ponen `jugar.py` (en `_trabajo\juego\`) y el launcher, como parte del
cliente. Windows la carga en lugar del d3d9 del sistema; ella le pasa todo al de verdad y agrega lo
de abajo **sin tocar un byte del exe**. Se maneja entera con **`eda_d3d9.ini`**, un archivo de texto al
lado del juego. Es del jugador: el launcher no lo pisa. Lo que pasa queda en **`eda_d3d9.log`**.

## El `.ini` por BLOQUES (12-nov)

`eda_d3d9.ini` está partido en bloques separados por `#####`, y cada bloque se prende o se apaga solo.
**Por defecto:** lo mínimo (tope de cuadros + server), la caja negra, el P2P y `[mazino]`; `[rui]` y
`[hysteria]` apagados (la columna «por defecto» de la tabla). Una mejora NUEVA viene prendida: ver
«Para la próxima PR».

| bloque | qué | clave | por defecto | riesgo | medido |
|---|---|---|---|---|---|
| **LO MÍNIMO** | ★ **el server**: el cliente busca el Broker de Corea de 2009 (`218.145.66.187:25000`, muerto) y la dll lo manda al nuestro | `[red] server=` (o el 3er argumento del launcher) | lo pone el launcher | bajo: un solo `connect` | §44 |
| | ★ **el login**: `"EDA_limpio.exe" <usuario> <ticket> [host:puerto]` → el bloque que el juego espera (PROTOCOLO §5.1); y las comillas si faltan | (sólo si vienen esos argumentos) | — | bajo | §45 |
| | **tope de cuadros**: EDA no trae; dibuja ~900 cuadros/s y la placa va al máximo | `[video] tope_fps` (el launcher la escribe) | **120** | bajo: un `Sleep` en el Present | §41 |
| | **contador** «FPS» arriba a la izquierda | `[video] mostrar_fps` (el launcher la escribe) | 0 | medio: dibuja en cada cuadro | — |
| | (todo lo de arriba menos el server y el login) | `[general] mejoras=0` | 1 | — | §48 |
| **CAJA NEGRA** | si el juego se cae, dice DÓNDE: ver abajo | `[cajanegra] activo` | **1** | nulo: sólo mira | §48 |
| **LLAMADAS SIN RESOLVER** (21-nov) | ★ pone en `EDA_limpio.exe` la llamada original de 17 sitios de la CRT que quedaron «sin resolver» al desempacar (IsValidLocale, GetCPInfo, GetStringTypeA…): sin esto el juego se cae al llegar a uno (medido: `0x7F4626` en una stage). Sólo si el exe es el conocido y en el sitio está la trampa. ★ Y corrige 3 llamadas de la CRT que el desempacado resolvió a la función EQUIVOCADA (0x7F4610 `RtlIntegerToChar` → `IsValidCodePage`: corría la pila 12 bytes, la 2ª caída de setlocale; 0x7F48D5 → `SetConsoleCtrlHandler`; 0x7E3789 → `GetDriveTypeA`), sólo si en el sitio está exactamente la llamada equivocada. `eda_apis.c`, pruebas `prueba_apis.c` y `prueba_apis.py` | `[apis] reparar` | **1** | bajo: 6 bytes verificados por sitio, la API de Windows de siempre | — |
| **DIAGNÓSTICO AUTOMÁTICO** (21-nov) | ★ SÓLO en TEST, con el login del launcher y una dirección: anota eventos chicos (escena, congelado ≥ 2 s, atrapado ≥ 15 s, fps cada 30 s, foco, conexiones al server, caída, cierre) y los manda solo, en segundo plano, a `/eda/diag` del server de prueba (HTTPS, firmados con una clave derivada del ticket: el ticket no viaja ni se guarda). Sin MAC, IP, nombre de la PC ni chat. Lo que no llega queda en `diag\pendiente.jsonl` (≤ 2 MB, ≤ 48 h). `eda_diag.c` + `eda_diag_nucleo.c`, pruebas `prueba_diag.c` y `prueba_diag.py` | `[diag] url` | **vacío** (apagado) | bajo: los ganchos sólo ponen una línea en una cola; un hilo de prioridad mínima manda cada 10 s | — |
| **TRADUCCIÓN EN MEMORIA** (23-nov) | ★ Con `idioma=es` (por defecto), sirve los XML traducidos: **1.** carpeta suelta `traducciones\es\<ruta>` junto al juego (para probar cambios sin recompilar), **2.** XML embebidos dentro de la DLL desde `traduccion/es/` (llegan a todos los jugadores sin carpetas extra), **3.** `Data.dat` original. Engancha las 16 llamadas SolFS verificadas (XML, texturas HGE, Lua y 3D LithTech) + 3 literales UTF-16 del mismo largo en `.rdata` (`LV%3d` → `Nv%3d`, `%dGold` → `%d Oro`). Sin tocar el exe, `Data.dat` ni `LTMsg.dll`. `idioma=en` / `off` o `[general] mejoras=0` vuelven al inglés original; `EDA_IDIOMA` pisa el `.ini`. `eda_traduccion.c`, prueba `prueba_traduccion.c` | `[traduccion] idioma` | **es** (embebido) | bajo: 7 prólogos y 16 llamadas verificadas de forma atómica antes de tocar nada | — |
| **P2P** (que los juegos se encuentren) | | `[p2p] activo` | **1** | | |
| | la identidad (MAC): el ticket de 20 del launcher la pisaba (`0x6229F0`, desviada en `0x4E767B`) | `[p2p] mac` | 1 | bajo: una llamada, verificada | §52 |
| | la IP de la casa = la de la red de verdad (no VMware / VirtualBox / Hyper-V / VPN) | `[p2p] ip_privada` | 1 | bajo: `gethostbyname` | §52 |
| | red inmediata (la de `[rui]`, prendida acá) | `[p2p] red_inmediata` | 1 | bajo | §42, §53 |
| **PARCHES DE RUI** (los nuestros) | | `[rui] activo` | **0** | | |
| | tope estricto: los cuadros fijos en todo el juego | `[rui] tope_estricto` | 1 | bajo | §42 |
| | red inmediata: un mensaje que llega mientras se espera el cuadro se atiende enseguida (ping de sala 1 ms a 60 cuadros/s) | `[rui] red_inmediata` | 1 | bajo | §42 |
| | anillo de vértices: los dibujos sin frenar la placa (dos juegos en una PC: sin él, 14 cuadros/s) | `[rui] anillo_vertices` | 0 | **alto**: toca CADA dibujo | §42–43 |
| **PARCHES DE HYSTERIA** (PR #6) | | `[hysteria] activo` | **0** | | |
| | letras completas: si se ven cortadas a la mitad, sus texturas empiezan en 32×32 (`0x770A64`, sólo si están los bytes originales) | `[hysteria] letras_32` | 1 | bajo: 5 bytes verificados | §49 |
| **PARCHES DE MAZINO** (PR #1, #5, #9, #38) | (su arreglo de la región ya está ADENTRO de `EDA_limpio.exe`, §37) | `[mazino] activo` | **1** | | §37, §57 |
| | botones Clan / Messenger / Options (lobby: `0x4F6061` → `0x4DF900`; Shop / Inventory / Refinery / Skill: el clic en la barra) → `/clan`, `/messenger`, `/opciones` al server | `[mazino] botones` | 1 | bajo: una llamada verificada + leer clics | §57 |
| | selección MÚLTIPLE en la bolsa (Ctrl+clic, la selección nativa: byte +0x248 de cada casilla) y «Sell» vende todas (`0x51A12B` → `0x54A990`) | `[mazino] seleccion_multiple` | 1 | bajo: una llamada verificada | §57 |
| | foco: EDA no se pausa al cambiar de ventana (WndProc `0x4026C0`) y no centra ni encierra el mouse si no está al frente | `[mazino] foco` | 1 | bajo | §57 |

⚠ **Las claves viejas** (`[video] tope_estricto`, `red_inmediata`, `anillo_vertices` / `buferes_rapidos`,
`[compat] letras_32`) **ya no se leen**: el `.ini` es del jugador (el launcher no lo pisa) y así nadie
arrastra lo que tenía prendido. Medido: un `.ini` viejo con todo prendido carga sólo el tope y el contador.

**Cada valor** se puede pisar con una variable de entorno, para probar sin tocar el `.ini`:
`EDA_MEJORAS`, `EDA_TOPE_FPS`, `EDA_MOSTRAR_FPS`, `EDA_RED_INMEDIATA`, `EDA_TOPE_ESTRICTO`,
`EDA_BUFERES_RAPIDOS` (el anillo), `EDA_LETRAS_32`, `EDA_SERVER`.

## Qué dll es (versionado, 19-nov)

Cada compilación dice sola qué es; nadie edita el código para eso.

| dato | de dónde sale |
|---|---|
| versión | `VERSION` (lo único que se cambia a mano, al sacar una versión) |
| commit | el **último commit que tocó el código que se compila** (`.c`/`.h`/`.def`/`VERSION` de esta carpeta, sin las `prueba_*`), no HEAD: commitear `exe/d3d9.dll`, una prueba, un `.py` o este LEEME no lo cambia, y el CI recompila la misma dll |
| sucio | cambios sin commitear (o archivos nuevos, o sin git) en ese código → `-dirty`, compilación **LOCAL**: nunca pasa por publicada |
| fecha | limpia: la del commit (UTC), así es reproducible · sucia: la hora real |
| build | `b` + 10 hex del sha256 del código (con LF): mismo código = mismo build en cualquier PC |
| entorno | **en el juego**, del server al que va (`[red] server`, `EDA_SERVER` o el 3er argumento del launcher): host de la PC o de la casa → LOCAL · puerto 35900 → TEST · 25900 → PROD · otro → OTRO |

- `version.py` escribe `eda_version.h` (no se commitea); `compilar.py` lo usa y deja **`d3d9.dll.json`** al lado de
  la dll: la identidad + md5/sha256/tamaño del archivo (el hash final no puede ir adentro: lo cambiaría).
- En el juego: el **aviso de arranque** (8 s, arriba a la derecha, no toma foco ni clics; `[version] aviso=0` lo
  apaga), la esquina de **Options** y la línea `identidad:` de `eda_d3d9.log` (y `entorno` en cada `connect`).
- `identificar.py RUTA\d3d9.dll [--esperado d3d9.dll.json | cliente-develop.json | eda.json | otra.dll] [--carpeta JUEGO]`:
  lee la marca `EDA-ID|…`, calcula los hashes y compara con lo que el esperado **realmente** trae. El manifiesto
  del launcher (`files`: `path`, `size`, `md5`; también firmado) no trae la identidad de la dll: su `version` es la
  de la release, y commit/build salen «no disponible» (se comparan los hashes). `--carpeta` revisa además ruta,
  tamaño y hash de cada archivo de la lista (el `.ini` y el `autoexec.cfg` del jugador sólo avisan).
  0 coincide · 1 manifiesto ilegible o incorrecto (sin la dll, sin hash, datos que no cierran) · 2 no coincide ·
  3 dll antigua sin identidad. Sin red.
- Pruebas: `python herramientas/dll_d3d9/prueba_version.py [d3d9.dll]` (también en el CI).

## El cliente de develop (para probar, 19-nov)

`exe/d3d9.dll` es la de la última release: la que sale del código de `develop` no estaba en ningún lado.
Ahora, **en cada fusión en `develop`, el CI la compila y la publica sola** en la release
**`cliente-develop`** del repositorio (trabajo `cliente-develop` de `.github/workflows/pruebas.yml`):

| archivo | qué es |
|---|---|
| `cliente-develop.json` | la lista: la identidad de la dll (como `d3d9.dll.json`) y `files` con `path`, `size`, `md5`, `sha256` (la forma del manifiesto del launcher) |
| `d3d9.dll` | la compilada por el CI desde ese commit (la misma del trabajo `dll`) |
| `eda_d3d9.ini` | el `.ini` por defecto de `compilar.py` |

`EDA_limpio.exe` no se copia ahí: la lista da su md5 y la dirección del que está en el repositorio, en ese
commit. El resto del cliente (Data.dat y demás) no cambia con `develop`.

```bat
py herramientas\dll_d3d9\canal.py bajar                 :: la dll y el .ini → _trabajo\dll\ (de ahí la toma jugar.py)
py jugar.py --server IP:35900 --como-launcher           :: el juego como lo abre el launcher, contra el server de prueba
py herramientas\dll_d3d9\canal.py bajar C:\copia\de\EDA :: o a una copia del juego (baja también el exe)
py herramientas\dll_d3d9\identificar.py _trabajo\dll\d3d9.dll --esperado cliente-develop.json
```

- En el juego, el aviso de arranque tiene que decir el commit de la lista y **TEST** (puerto 35900).
- El `.ini` es del jugador: si ya está y es distinto, `bajar` no lo pisa (lo dice).
- ⚠ Es un canal de **prueba**: la lista no está firmada (la de los jugadores sí). No toca `main`, ni el
  launcher, ni lo que reciben los jugadores: eso sigue llegando con una release del cliente.
- Un launcher de prueba propio sólo necesita esto: bajar `cliente-develop.json`, comparar los `sha256` con
  lo que tiene, bajar lo distinto de `base` + `path` (o de `url`, si la entrada la trae) y abrir
  `EDA_limpio.exe` con `EDA_SERVER=host:35900` (o `[red] server=` en el `.ini`).

## Si a alguien se le cae el juego

1. Que mande **`eda_d3d9.log`**, y si existen, `EDA_limpio.rpt` y `EDA_limpio.dmp` (el informe del
   propio juego). Están al lado del exe.
2. En el log, la **caja negra** dice:
   ```
   ⛔⛔ [cajanegra] EXCEPCION 0xC0000005 en NUESTRA-d3d9+0x25F3 · escribe en 0x00000010 · … · ★ ES EN NUESTRA DLL
      [cajanegra] eax=… ebx=… (los registros)
      [cajanegra] la pila (de la más cercana a la más lejana): d3d9-de-Windows+0x4BB50 · … · exe 0x0054C0D1 · …
   ```
   - **`NUESTRA-d3d9`** = la culpa es nuestra.
   - **`exe 0x…`** = el juego de 2009: se busca esa dirección en el exe.
   - **`d3d9-de-Windows`** o el nombre de otra dll = el driver o Windows.

   Guarda hasta 3 por arranque. Dice «primera oportunidad» porque puede ser una que el juego mismo
   maneja. El log no se pisa al reabrir; pasado 1 MB, el viejo pasa a `eda_d3d9.anterior.log`.
3. **Para separar «culpa de la dll» de «culpa del juego»:** `[general] mejoras=0`. Si con eso no se
   cae, es el tope o uno de los bloques: se prenden de a uno (`[rui]`, `[hysteria]`, `[mazino]`) hasta
   encontrarlo.

## Para la próxima PR (cómo se agrega algo a la dll)

★ Por qué todo va en la dll y no en el exe, y cómo se revisa un PR: `documentacion/POR_QUE_LA_DLL.md`.

- **Una mejora nueva va en el BLOQUE de su autor** (`[rui]`, `[hysteria]`, `[mazino]`, o uno nuevo con el
  nombre de quien la trae), con su clave. **Viene PRENDIDA por defecto en el código** (el `.ini` es del
  jugador y el launcher no lo pisa: apagada no le llegaría a nadie); la clave sirve para apagarla, y
  `mejoras=0` también. **Antes de publicarla a los jugadores (una release del cliente), se mide en dos
  PCs, una que no sea la del autor.** Lo que hoy figura apagado en la tabla sigue como está. (Decidido
  el 14-nov; antes era «apagado hasta medirlo en más de una PC».)
- **Si cambia lo que hace una clave que ya existe, se cambia el NOMBRE de la clave.** El `.ini` de cada
  jugador queda con el valor viejo, y el launcher no lo pisa.
- Que anote en `eda_d3d9.log` qué hizo (o por qué no), y que no haga nada pesado en `DllMain`.
- **Parches al código del exe en memoria** (como el de las letras de la PR #6): sólo con su clave, y
  verificando antes los bytes originales (si no coinciden, no se toca y se anota).
- La fila en la tabla de arriba, y la medición en `documentacion/MEDICIONES.md`.
- Probar la caída a propósito: `EDA_PROBAR_CAJA=1` hace caer a NUESTRA dll en el cuadro 60, y el log
  tiene que decir «★ ES EN NUESTRA DLL». Sin la variable, no se cae (el revés).

```bat
py herramientas\dll_d3d9\compilar.py            :: compila (Zig 0.16, la receta de R2Beat) → _trabajo\dll\ (+ el .ini por defecto)
py herramientas\dll_d3d9\compilar.py --poner    :: y la pone al lado del juego
py herramientas\dll_d3d9\compilar.py --sacar    :: la saca (el juego vuelve al d3d9 de Windows)
py jugar.py --sin-dll                           :: jugar sin ella (⚠ sin ella no hay login ni server: sólo con jugar.py)
```

Para diagnosticar Direct3D se puede usar **DXVK** (su panel en pantalla: cuadros, dibujos, uso de la
placa) en lugar de esta dll; ver MEDICIONES §41. DXVK pide Vulkan, que muchas PCs modestas no tienen:
por eso la solución es esta dll, que anda con cualquier D3D9.


### Selector de Stage (candidata 0.5.1)

Las imágenes de las flechas del mapa solapan parte de los botones y podían recibir el doble clic sin abrir el Stage. La DLL excluye esas imágenes del hit-test exclusivamente en la escena del selector, conservando sus dibujos y los rectángulos de los botones. No cambia el escalado, el mouse de combate ni los tiempos del doble clic.

Se puede desactivar con `[mazino] selector_stage=0` en eda_d3d9.ini. Respeta también los interruptores generales de mejoras/mazino. El parche comprueba las dos llamadas y la firma de TestPoint antes de instalarse; con un EXE incompatible no se aplica. El registro dice `selector_stage: flechas sin captura de clics (2/2 llamadas)`.

La versión numérica de la candidata es 0.5.1, identificada además por commit/build. Esta PR no declara una entrega estable ni publica etiquetas. No se atribuye al arreglo un parpadeo general que no se haya reproducido.

Prueba de regresión: `zig cc -o prueba_selector prueba_selector.c` y ejecutar el resultado. Reproduce la imagen 14011 interceptando el borde del botón 14006; comprueba el destino corregido, centros, bordes y que otras escenas/controles se conserven.
