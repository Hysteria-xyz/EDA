# Más de 3 jugadores por sala — de dónde sale el 3 y qué hace falta

> 24-nov-2026. Estático (exe `EDA_limpio.exe` md5 0799387e, `Data.dat` extraído, el código del server y de la dll):
> ✅ verificado en el exe / los datos / el código · 🟡 deducción · ❌ no encontrado · ⏳ falta medir con el juego.

## 0 · En una línea

**El 3 no es un límite del juego: es el máximo de las stages en FÁCIL.** Cada escenario trae su máximo en
`data/scenariolist.xml`: **Fácil = 3, Normal = 5, Difícil = 8**. El cliente está hecho para **8** (8 filas en la
sala, 8 marcos de compañeros en el HUD, 8 «Player Start» por mapa, listas dinámicas) y nuestro server respeta el
máximo que manda el cliente. **Hoy, sin tocar código, una sala de Normal admite 5 y una de Difícil 8.** Lo único
que falta del lado del server es que un cambio de escenario/dificultad DENTRO de la sala actualice ese máximo (§4).

## 1 · De dónde sale el 3 — ✅

| dónde | qué dice | evidencia |
|---|---|---|
| `Data.dat:data/scenariolist.xml` | `<SCENARIO ID="1011" … MAXPLAYER="3"/>`: los 150 escenarios; **50 × 3 (último dígito 1 = Fácil), 50 × 5 (2 = Normal), 50 × 8 (3 = Difícil)** | l.7: 1011 → 3; 1012 → 5; 1013 → 8 (contado por el último dígito del ID: sin excepciones) |
| los XML de cada escenario (`data/scenario/*/chapter1_*.xml`) | ❌ no tienen `MAXPLAYER` | 151 archivos revisados |
| el exe | lee `MAXPLAYER` como **un byte** en `+0xC0` del registro de cada escenario | `0x64D14E push 0x89EFC0` («MAXPLAYER») → `0x64D174 mov [esi+0xC0], al` |
| la sala (89 B) | `+0x2F` = máximo de jugadores; el lobby lo muestra «1/3» (MEDICIONES §19) | `servidor/salas.py:32` |
| nuestro server al crear | copia la sala que manda el cliente; sólo si `+0x2F` llega en 0 pone 3 | `servidor/salas.py:920-921` (y la prueba de red, `red.py:588`) |
| nuestro server al entrar | sala llena = `miembros >= sala[0x2F]` | `salas.py:243` (0x101F), `:720` (0x1025 entrada rápida), `:746` (0x1019) |

🟡 No ubiqué la instrucción que copia `+0xC0` del escenario al `+0x2F` de la sala en «Create Stage» (las 7
lecturas de `byte [+0xC0]` no la tienen al lado); el resultado sí está medido: una sala de la 1011 Fácil sale
«1/3» en el lobby y su sala de espera muestra 3 filas (PVP_BATTLE_UI.md §9, 24-nov).

## 2 · El cliente con más jugadores — ✅ sin límite duro hasta 8

| pieza | qué hace | evidencia |
|---|---|---|
| lista de miembros (`cuenta+0x240`) | `std::vector` de registros de 0x36F, se recorre de `+0x64` a `+0x68` buscando el número en `+5`: **dinámica** | `0x61C110` |
| HUD de compañeros (`ebp+0xF8`) | `std::map` (búsqueda `0x6127B0`): **dinámico** | `0x612A90` |
| marcos de compañeros en la stage | **8** popups «파티정보» (información del grupo), índices 8100…8800 | `Data.dat:menu/international/gamescene.xml:536-653` |
| filas de la sala de espera | `BUTTONEXLIST 300` con **`VISIBLECNT="8"`** (301…308); muestra tantas como el máximo de la sala | `waitroom_mission.xml:116-131`; medido 24-nov |
| apariciones | **8** «Player Start» en cada mapa del capítulo 1 (`chapter1_1..10.dat`, `chapter1_1t.dat`); `InitPlayGame("Player Start")` | PVP_ARQUITECTURA.md, contado en los `.dat` |
| tamaño de los mensajes | el paquete del juego tiene 4 KB adentro pero **crece**: `0x7432B0` reserva más (bloques de 1 KB, copia lo que había). El `0x1020` de entrar a una sala lleva 0x32C B por miembro (~6 KB con 7 adentro): entra. Tope: el `u16` del largo (65 535) | `0x7425D0` (capacidad `+0x1008 = 0x1000`), `0x7432B7 cmp [ebp+0x1008], eax` → realloc `0x7E3CC5` |
| `0x1062` (baja de NPC con EXP) | compara el número con el máximo de la sala (`+0x273` = sala `+0x2F`): un número ≥ máximo se ignora | `0x547474` |
| comparaciones sospechosas | `0x54841A cmp [esp+0x48], 8` en `0x1058` es la capacidad de una cadena (`mov …, 7` después), **no** jugadores | desensamblado |

❌ No encontré en las funciones de miembros, HUD, P2P (`0x550BE0`), largada (`0x54F170`), resultados
(`0x548AF0`, `0x546CA0`, `0x546960`), entrar/crear sala (`0x543640`, `0x543500`) ni cambios (`0x54FC80`,
`0x5482A0`) ningún `cmp` con 3, 4, 5 u 8 que limite jugadores.

## 3 · Nuestro server y la dll — ✅ nada asume 3

- **server**: el máximo es el de la sala (`sala[0x2F]`); `dar_numero` da 0…255 (`estado.py:44`); `pares()` arma el
  `0x1059` para todos contra todos; el relay da un puerto por conexión (`RELAY_BASE + 1 + n`, hasta
  `EDA_MAX_CONEXIONES` = 200, `red.py:54`); el tope del server entero es `EDA_MAX_JUGADORES` = 100 (`config.py:96`).
  Las pruebas multijugador ya usan 3 conexiones (501–503).
- **⚠ login abierto (casa / pruebas locales)**: las cuentas automáticas son **4** (`cuentas.py:42`:
  rui, kai, mio, ren). Con el login del portero (el VPS) no hay ese tope.
- **la d3d9.dll**: ❌ nada asume ≤ 3 jugadores (búsqueda de miembros, `0x240`, `0x36F`, `0x273`, arreglos fijos en
  `eda_*.c`): la dll no toca la lista de jugadores. La capa PvP y los equipos usan el número % 2 (sirve hasta 8).

## 3b · HECHO y medido (24-nov) — ✅

- **server**: `salas.maximo_sala(escenario, del_cliente, adentro)`: `EDA_JUGADORES_SALA` (1..8) manda para todas
  las salas; si no, el que manda el cliente; si llega 0, la regla de `scenariolist.xml` (1 → 3, 2 → 5, 3 → 8). Nunca
  menos que los que ya están adentro ni más de 8. Lo usan `crear_sala` y el `0x104B` tipo 1 (cambio de escenario,
  que antes dejaba el máximo viejo: §4.1 ya resuelto). Pruebas: `pruebas_jugadores_sala` (7).
- **la dll**: sin cambios para esto (no hacía falta).
- **prueba en vivo con 4 clientes en una PC** (`EDA_PVP_N=4 dos_clientes.py iniciar --hex --jugadores 4`): rui,
  kai, mio y ren en una sala de **Fácil** con máximo 4 → las 4 filas en la sala de espera, F9 → `0x105E` a los 4,
  los 4 en la stage (Chapter1_1), fin → `0x1073` (resultados) y `0x1072` (volver a la sala) a los 4, los 4 de
  vuelta en la sala; ningún juego colgado, 99–120 cuadros/s en cada uno.
- **Para jugar de a 4+ en Fácil**: arrancar el server con `EDA_JUGADORES_SALA=4` (o hasta 8). Sin la variable todo
  queda como en 2009.
- ⏳ sigue sin medir 5–8 de verdad (hace falta más de una PC).

## 4 · Lo que faltaba (chico)

1. ✅ (resuelto en §3b) **`0x104B` no actualiza el máximo** (`salas.py:805-827`): cambia el escenario (`+0x28`) o la dificultad
   (`+0x2C`) de la sala pero deja el `+0x2F` con el de antes. Una sala creada en Fácil (3) y pasada a Difícil
   sigue en 3; creada en Difícil (8) y pasada a Fácil queda en 8. **Propuesta**: con el tipo 1 (escenario), poner
   `+0x2F` = máximo del escenario nuevo con la regla de `scenariolist.xml` (último dígito 1 → 3, 2 → 5, 3 → 8),
   nunca menos que los que ya están adentro; y usar la misma regla en vez del 3 fijo de `crear_sala` cuando llega
   en 0. Con su prueba y su revés.
2. **Para jugar hoy**: crear la sala en **Normal (5)** o **Difícil (8)**. Se habilitan terminando la Fácil de esa
   stage (la cadena 1011 → 1012 → 1013, PROTOCOLO §5.7) o con el GM `/desbloquear [personaje]` (todas las stages,
   al volver a entrar al lobby).
3. **(Opcional) Fácil con más de 3**: servir un `scenariolist.xml` con otro `MAXPLAYER` por la capa de la dll
   (como la arena). 🟡 Lo permite el mecanismo; ⏳ no se midió, y la dificultad de Fácil está pensada para 3.

## 5 · Qué NO se sabe sin medir (⏳)

- El P2P con 5–8: cada juego habla por UDP con todos (`0x1059` a cada par); se midió con 2–3. La carga de red y de
  cuadros con 8 en una stage.
- Que el HUD muestre bien los 8 marcos y que las cartas / AWARD (`0x1072` N jugadores, `0x1073` M jugadores) con 8
  se vean completos.
- Que el máximo que el cliente pone al crear salga de `MAXPLAYER` también en Normal/Difícil (medido sólo en Fácil).

## 6 · Cómo probarlo

- `dos_clientes.py` abre 2 (A y B). Con el login abierto se puede llegar a **4** en una PC (rui, kai, mio, ren):
  agregar instancias C y D (mismo espejo de enlaces duros; ~1 GB de RAM y la placa: con el tope de 120 cuadros y
  el anillo, dos juegos ya andaban a 120 cuadros/s, MEDICIONES §42).
- Pasos: `/desbloquear` → sala en Normal → entran 4 → F9 → la stage con 4 → fin → sala. Mirar: las 4 filas, los
  marcos del HUD, el ping de cada par en la sala (sin `-1000`), el registro del server (`0x1059` por par).
- Para 5–8 hacen falta dos PCs o el server de prueba con varias personas.
