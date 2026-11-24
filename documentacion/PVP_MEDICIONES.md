# PvP — mediciones (etapa 0)

> Rama `feature/pvp-system`. Base: [PVP_INVESTIGACION.md](PVP_INVESTIGACION.md). Todo lo de acá se midió en un
> entorno local (una PC, dos clientes, server propio). ✅ = medido · ⏳ = falta medir · ❌ = medido que NO ·
> 🚫 = bloqueado por otra cosa · 🟡 = deducción. **Nada del PvP cuenta como funcionando hasta verlo con dos
> clientes reales.**

## 1 · El entorno de dos clientes (etapa 0.1) — ✅ medido el 24-nov

Herramientas nuevas, todas en `herramientas/pvp/` (lo experimental, aparte de lo definitivo). Ninguna escribe
en el juego: el exe, `Data.dat` y `_trabajo\juego` no se tocan.

| herramienta | qué hace | control |
|---|---|---|
| `dos_clientes.py` | prepara dos carpetas de juego, levanta un server propio, abre los dos juegos, los lleva a la stage, cierra y junta los registros | ✅ 11/11 |
| `vida.py` | busca la vida (HP) en la memoria de cada juego (dos pasadas, sólo lectura) y la mira cambiar | ✅ 7/7 |
| `udp_combate.py` | captura TODO el UDP de la partida de los dos juegos (datagramas enteros) con MARCAS escritas a mano, y resume qué aparece después de cada marca | ✅ 5/5 |

Un cambio en una herramienta definitiva: `herramientas/multi.py` separa en `desde_el_lobby()` los pasos
lobby → sala → partida que ya hacía (mismo comportamiento), para que `dos_clientes.py llevar` los use.

### 1.1 · Conflictos encontrados y cómo se evitan

| riesgo | qué pasaba / pasaría | solución |
|---|---|---|
| archivos compartidos | dos juegos en `_trabajo\juego` escriben el mismo `eda_d3d9.log`, `NetTrace.log` y `autoexec.cfg` | una carpeta por juego (`%USERPROFILE%\EDA_pvp\A` y `\B`); lo grande (`Data.dat`, 5 archivos) son **enlaces duros** a `_trabajo\juego` (no ocupan lugar) y lo chico se copia (53) |
| OneDrive | 300 MB por carpeta subiendo a la nube | `EDA_pvp` va fuera de OneDrive |
| ⚠ carpeta redirigida | lanzado desde un programa empaquetado (la app de escritorio), `%LOCALAPPDATA%` se redirige a `AppData\Local\Packages\…\LocalCache` (medido con `fsutil hardlink list`): otra terminal no la vería | la base es `%USERPROFILE%\EDA_pvp` (o `EDA_PVP_DIR`) |
| server / puertos | `jugar.py` usa 25900 y el relay de siempre 26000 | server propio en **27900** (HTTP 27901), relay UDP **28000…28200** |
| cuentas | las de siempre (`_trabajo\servidor\cuentas`) | cuentas aparte en `EDA_pvp\estado`: **rui** (juego A) y **kai** (juego B), nivel 25, GM las dos (`/fin`, `/oro`) |
| puertos UDP de los juegos | los dos no pueden usar 57654 | el segundo toma otro solo (MEDICIONES §19) |
| MAC (identidad P2P) | lanzado sin comillas, el exe pisa su MAC (PROTOCOLO §5.1) | `dos_clientes.py` lanza con la ruta entre comillas |
| versión del cliente | ⛔ corregido el 24-nov: `exe\d3d9.dll` del repo es la del **Punto 4** (md5 `d7df418b`, PR #52), no la 0.5.4, y no carga archivos sueltos | exe del repo + la dll **0.5.4 de la release «cliente-develop»** (md5 `b3ecd9f9`, compilada de `f5c9ccb`), verificada con su lista: `dos_clientes.py preparar --dll` |

### 1.2 · Lo medido al validarlo (sesión `20261124-060133`)

- `iniciar`: server + los dos juegos. **La dll entra sola hasta el lobby** con `EDA_SERVER` (server, personaje,
  lobby sin un clic): A = **rui**, B = **kai**, cada uno ve al otro en la lista del lobby (`foto_juego.py --pid` de cada uno).
- `llevar partida`: sala «Duelo de prueba» (A anfitrión) → listo → F9 → **los dos en la stage 1011**, cada uno
  ve al otro con su nombre (`_trabajo\fotos\multi_partida.png`).
- Camino P2P con `--p2p auto` en la misma PC: **relay en los dos sentidos** (`sala: a #2 le doy #3 por relay`):
  el anfitrión no manda su `0x3006` (config.py:52). ⇒ todo el UDP de la partida pasa por el relay local.
- Hay UDP entre los dos: `UdpMsgCnt:128` en el `NetTrace.log` de B.
- `cerrar`: 0 procesos vivos, y en la carpeta de la sesión `server.log`, `A_eda_d3d9.log`, `A_NetTrace.log`,
  `B_eda_d3d9.log`, `B_NetTrace.log`, separados.
- 🟡 En el lobby, al lado de «Scenario», hay una **segunda pestaña vacía** (sin texto): coincide con
  `ChannelLobby_BattleModeBtn` (`STRID="0"`, `channellobby.xml:126`). Se estudia en la etapa 0.4.

### 1.3 · Inicio y cierre (siempre igual)

```bat
py herramientas\pvp\dos_clientes.py preparar        :: una vez, y cada vez que cambie exe\ o _trabajo\juego
py herramientas\pvp\dos_clientes.py iniciar         :: server + juegos A y B (A a la izquierda) → los dos en el lobby
py herramientas\pvp\dos_clientes.py llevar partida  :: sala, listo, F9 → los dos en la stage 1011
py herramientas\pvp\dos_clientes.py estado
py herramientas\pvp\dos_clientes.py cerrar          :: cierra todo y deja los registros en EDA_pvp\registros\<hora>\
```

**La stage controlada** = la primera del selector, **1011 (Easy)**: al aparecer no hay monstruos cerca (salen
con los disparadores del guion, al avanzar), así que los dos personajes quedan solos y frente a frente.

---

## 2 · Procedimiento de la medición E1: ¿un jugador daña a otro? (etapa 0.2) — ⏳ necesita tus manos

Se mira lo mismo **de tres maneras a la vez**: la pantalla (vos), la vida en la memoria de los dos juegos
(`vida.py`) y el tráfico UDP (`udp_combate.py`). Abrí **tres consolas** en la carpeta del repo.

### Paso 0 — que rui y kai tengan vidas DISTINTAS

Los dos son nivel 25 recién creados: tienen la misma vida y no se podría saber cuál número es de quién.
1. Consola 1: `py herramientas\pvp\dos_clientes.py iniciar`
2. En el juego **B (kai)**, en el lobby: abrí la ficha del personaje y poné **todos los puntos libres en
   Constitution** (botones «+») y salí de la ficha. Eso sube su vida máxima.

### Paso 1 — a la stage

3. Consola 1: `py herramientas\pvp\dos_clientes.py llevar partida`
4. Anotá la **vida de rui** (en A) y la **de kai** (en B) tal como la muestra el HUD (arriba a la izquierda). Si
   el HUD no muestra el número, decímelo y busco otra forma.

### Paso 2 — encontrar la vida en memoria (control positivo con un monstruo)

5. Consola 1 (reemplazá los números por los que anotaste):
   ```bat
   py herramientas\pvp\vida.py buscar A <vida de rui> --nombre rui
   py herramientas\pvp\vida.py buscar B <vida de kai> --nombre kai
   py herramientas\pvp\vida.py buscar B <vida de rui> --nombre rui_en_kai
   py herramientas\pvp\vida.py buscar A <vida de kai> --nombre kai_en_rui
   ```
6. Con **rui** (A), caminá hacia adelante hasta que un monstruo le pegue UNA vez, y volvé atrás. Anotá la
   vida nueva y filtrá:
   ```bat
   py herramientas\pvp\vida.py filtrar A <vida nueva de rui> --nombre rui
   py herramientas\pvp\vida.py filtrar B <vida nueva de rui> --nombre rui_en_kai
   ```
   Si «rui» queda con 0 candidatos o con más de 10, repetí un golpe más y otro `filtrar`. (Si `rui_en_kai`
   queda en 0 también es un dato: el juego de kai no tiene la vida de rui como número suelto.)

### Paso 3 — las pruebas, con marcas

7. Consola 2: `py herramientas\pvp\vida.py mirar 600`
8. Consola 3: `py herramientas\pvp\udp_combate.py capturar 600`. En esta consola, **antes de cada prueba**,
   escribí la palabra de la marca y Enter.
9. Con los dos personajes cerca uno del otro, lejos de los monstruos:

| marca | qué hacés | qué mirás y anotás |
|---|---|---|
| `quieto` | nada, 10 s | (la línea de base del UDP) |
| `choque` | kai camina **contra** rui (W), 3 s | ¿lo atraviesa o choca? |
| `aire` | kai pega 3 veces (clic) **al aire**, lejos de rui | (cómo se ve un ataque que no toca nada) |
| `kai_pega` | kai pega 5 veces **de frente y pegado** a rui | en A y en B: ¿rui hace la animación de golpe? ¿sale número de daño o sonido? ¿baja la barra de vida de rui? |
| `rui_pega` | lo mismo al revés: rui le pega a kai | lo mismo para kai |
| `arma` | kai cambia de arma (F) y repite `kai_pega` | ¿cambia algo? |
| `dash` | kai prueba el Dash hacia rui (el que gasta 24 de MP, si sabés cómo sale) | ¿lo empuja, lo daña? (las demás habilidades hoy no salen: MEDICIONES §34) |
| `monstruo` | rui deja que un monstruo le pegue | (el control: así se ve un daño de verdad, en vida y en UDP) |

10. Cortá las consolas 2 y 3 (Ctrl+C) y `py herramientas\pvp\dos_clientes.py cerrar`.
11. Pasame: el nombre de la carpeta de la sesión (`EDA_pvp\registros\<hora>`) y lo que viste en cada fila.
    Con eso analizo `vida.jsonl`, `udp_*.jsonl` (`udp_combate.py resumen`) y los registros.

### 2.1 · Cómo se va a interpretar

| lo que se ve | quiere decir | lo siguiente |
|---|---|---|
| baja la vida de rui en A (y/o en `rui_en_kai`) con `kai_pega`, no con `aire` | ✅ **hay daño entre jugadores** en el motor | medir quién lo decide: si cambia primero en el juego del que pega o del que recibe (horas de `vida.jsonl`) y qué datagrama lo lleva |
| rui hace la animación de golpe pero la vida no baja | el golpe se detecta pero el daño se descarta | buscar el filtro: punto de ruptura sobre la escritura de la vida (la dirección del paso 2) y subir por quién la llama |
| nada (sin animación, sin vida, el UDP de `kai_pega` igual al de `aire`) | el ataque **no considera a otro jugador como objetivo** | buscar cómo el cliente elige objetivos: qué funciones recorren las entidades al pegar (con la dirección de la vida del monstruo como ancla) |
| `choque`: lo atraviesa | los jugadores no tienen colisión entre sí (🟡 típico de un co-op) | anotar: limita el PvP cuerpo a cuerpo, no lo impide |
| `rui_en_kai` nunca cambia, ni con el monstruo | el juego de kai no guarda la vida de rui como número propio (o se actualiza de otra forma) | buscarla con otro tipo (`--tipo i32`) o por porcentaje |

## 3 · Matriz de funcionalidades

| funcionalidad | estado | evidencia / qué falta |
|---|---|---|
| dos clientes independientes en una PC | ✅ | §1.2 |
| dos cuentas distintas (rui / kai) | ✅ | §1.2, fotos del lobby |
| los dos en la misma stage, viéndose | ✅ | `multi_partida.png` |
| inicio y cierre reproducibles, registros por cliente | ✅ | §1.2 |
| UDP entre los dos juegos (por el relay local) | ✅ | `UdpMsgCnt`, «por relay» |
| la vida en memoria | ✅ | entidad `+0x20C` (float): `entidades.py` la lee en `OnDamaged`, `SetHP` y la que llega por red (84.6 con nivel 25 y 0 puntos). El HUD no muestra números: `combate_auto.py` mide la barra (221 px llena) |
| ID de entidad de cada jugador | ✅ | rui = 0, kai = 1 (`vida_red`, `GetPlayerID`) |
| grupo de cada jugador | ✅ | `+0x40` (máscara): los dos nacen en `0x1`; con `SetEntityGroup` kai pasó a `0x4` en los DOS clientes |
| colisión entre jugadores | 🟡 no hay | kai caminó 3 s contra rui y quedó superpuesto, en las dos pantallas (sesión `-062450`, fotos `03_choque`) |
| **daño entre jugadores con grupos distintos** | ✅ | sesión `-064447`, manejado a mano: 9 golpes en los dos sentidos, 15–22 de daño, `OnDamaged` con atacante y víctima en los dos clientes, vida sincronizada por red (PVP_PROTOTIPO.md T05/T06) |
| daño entre jugadores con el MISMO grupo (sin cambio) | ❌ no hay | T01 a mano (sesión `-070421`): más de 10 golpes de cada lado, sin reacción, barras llenas, cero `OnDamaged` |
| muerte de un jugador a manos de otro | ✅ | `muerte` en los dos clientes; el server recibe `0x1065` con **quién lo mató** (`01 · 00000000` = kai, por rui) |
| revivir después de una muerte PvP | ✅ | `0x106A` → `0x106B` (moneda), vida otra vez 84.6 en los dos |
| fin controlado de la arena | ✅ | `GetAlivePlayerNum` 2 → 1 → `OnEnd` → `0x1064` de los dos, 5 s después de la muerte |
| habilidades de área contra jugadores | 🚫 | las habilidades no se lanzan en la partida (MEDICIONES §34) |
| contenido del UDP de combate | 🟡 | familias por largo+tipo (`48000340` 76 B, `0c000540`, `190051c3`/`52c3` con la MAC): falta separar el golpe |
| el PvE sigue igual sin la arena | ✅ | T08, sesión `-070959` |
| sala de duelo, ganador PvP, vuelta al lobby | ⏳ | el fin hoy paga el resultado PvE de 1011 |

## 4 · Registro de sesiones

| sesión | qué | resultado |
|---|---|---|
| `20261124-060133` | validar el entorno: iniciar → lobby → `llevar partida` → cerrar | ✅ §1.2 |
| `20261124-062450` | stage ORIGINAL, sin cambios: T03 choque, T01 automático (kai y rui pegan), UDP y diagnóstico de entidades | choque: superpuestos · T01: barras sin cambio, ningún `OnDamaged` (golpe no comprobado) · rui no se movió con `control_partida` |
| `20261124-063812` | arena instalada con la dll del repo (Punto 4) | ⛔ corrió el guion original: esa dll no tiene carpeta suelta |
| `20261124-064128` | arena + grupos, dll 0.5.4 | ✅ guion servido · `SetEntityGroup(1, 3)` en los dos · rui muere (entidad 1 lo mata) · fin y cartas · ⚠ los ataques fueron a mano (no registrado quién) |
| `20261124-064447` | arena + grupos, dll 0.5.4, **combate a mano de los dos lados** | ✅ daño entre jugadores en los dos sentidos, sincronizado; kai muere; `0x1065` con el atacante; revive; fin |
| `20261124-070421` | arena **sin** grupos, dll 0.5.4, combate a mano (T01) | ✅ cero daño: sin reacción, barras 221/221, cero `OnDamaged` / `0x1063` / `0x1065` |
| `20261124-072844` … `-074909` | server con `--pvp` + arena con grupos, sin teletransporte, ataques AUTOMÁTICOS de kai | ✅ el server reconoce el duelo · ⛔ encontrado: los dos clientes eligen jugadores distintos para `SetEntityGroup` y los dos quedan en `0x4` (corregido; en `-074909` rui `0x1` y kai `0x4` en los dos) · ⏳ ningún golpe automático llegó (la entrada automática con la dll 0.5.4 es poco confiable: PVP_PROTOTIPO.md §5) |
| `20261124-070959` | arena QUITADA, stage normal a mano (T08) | ✅ guion original; golpes jugador↔monstruo en los dos sentidos, 10 bajas, 2 muertes y 2 revividas; 0 golpes entre jugadores |
