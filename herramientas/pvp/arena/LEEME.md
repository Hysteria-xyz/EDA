# Arena PvP experimental (stage 1011)

> Experimental. Sólo para las instalaciones de prueba de `herramientas/pvp/dos_clientes.py`. **No es el juego
> original y no se reparte.** ✅ Probada con dos clientes el 24-nov (documentacion/PVP_PROTOTIPO.md).
>
> ⚠ Hace falta la `d3d9.dll` 0.5.4 (la de la release «cliente-develop», md5 `b3ecd9f9`):
> `gh release download cliente-develop --repo r2beatlatino/EDA --dir %USERPROFILE%\EDA_pvp\dll_develop` y
> `dos_clientes.py preparar --dll %USERPROFILE%\EDA_pvp\dll_develop`. La de `exe\` del repo (Punto 4, `d7df418b`)
> no tiene la carpeta suelta: con ella corre el guion ORIGINAL (medido, sesión 20261124-063812).
> Instalar: `dos_clientes.py recursos instalar` (sin grupos) o `recursos instalar --grupos` (T04/T05).

## Qué reemplaza

`data/scenario/easy/chapter1_1_e.lua` = el guion de la **stage 1011 (Easy)**, la primera del selector. Lo dice
`data/scenario/easy/chapter1_1_e.xml` de `Data.dat`: `<SCRIPT PATH="Data\Scenario\Easy\Chapter1_1_E.lua"/>` y
`<MAP PATH="Maps\Chapter1\Chapter1_1.dat"/>`. Las otras dificultades usan otros archivos (`_n`, `_h`): no cambian.

## Cómo se instala (sin tocar Data.dat)

La `d3d9.dll` (`herramientas/dll_d3d9/eda_traduccion.c`) intercepta cada archivo que el juego abre de `Data.dat` y
busca primero uno suelto en

```
<carpeta de la d3d9.dll>\traducciones\<idioma>\<ruta en minúsculas>
```

(`tr_armar_ruta`, l.217-248; `tr_normalizar_ruta` pasa la ruta a minúsculas y con `\`, l.179-214). Para esta arena:

```
EDA_pvp\A\traducciones\es\data\scenario\easy\chapter1_1_e.lua
EDA_pvp\B\traducciones\es\data\scenario\easy\chapter1_1_e.lua
```

Condiciones (medidas en el código, no en el juego):
- el idioma tiene que estar activo: `[traduccion] idioma=es` en `eda_d3d9.ini` (es el valor por defecto, l.410)
  y `[general] mejoras=1`; con `en`, `off` o vacío no se engancha nada (l.820-824);
- la carpeta `traducciones\es\` tiene que existir **al arrancar el juego** (l.826-838): se mira una sola vez;
- lo que no esté suelto sigue saliendo del español embebido en la dll y, si no, de `Data.dat` (l.492-507): el
  resto del juego queda igual;
- `eda_d3d9.log` anota cada archivo servido suelto: `[traduccion] #n (suelto) → data\scenario\easy\chapter1_1_e.lua`
  (l.451-461). **Esa línea es la prueba de que se cargó.**

## Qué hace, fase por fase

| fase | cómo | qué se ve (server con `EDA_LOG_HEX=1`: `0x105C` con el nombre) |
|---|---|---|
| carga | `InitPlayGame("Player Start")` como el original; **sin briefing, sin monstruos, la puerta no se abre** | — |
| teletransporte (3 s) | `TeleportToMarker(GetPlayerID(i), …)`: J1 → `Player Start 04`, J2 → `Player Start 08` | `PvP_Teleport` |
| cuenta regresiva | 5 × `ShowTestMsg("Duelo en n")` cada 1000 ms | `PvP_Cuenta` × 6 |
| pelea | sondeo de vivos y jugadores | `PvP_Pelea`, `PvP_Vigilar`, `PvP_Limite` (300000) |
| cambio de vivos | `GetAlivePlayerNum()` | `PvP_Vivos2` / `PvP_Vivos1` / `PvP_Vivos0` |
| desconexión | `GetPlayerNum() < 2` | `PvP_Desconexion` |
| fin | vivos ≤ 1, desconexión o 5 min → mensaje → `OnEnd` → `SendEvent()` | `OnEnd` (5000) y después el `0x1064` del máster |
| diagnóstico | cada 2 s, en pantalla: fase, vivos, id y `manager:GetHP(id)` de cada jugador **según ese cliente** | `PvP_Diag` (2000) |
| grupos (T04) | `PVP_GRUPOS = false`: no se llama nada | `PvP_Grupos` sólo si se prende |

**Límites del combate:** los dos quedan en la sala de inicio. Su puerta (`DoorL01`) sólo se abre con
`DoorSwitch_01` del original, que acá no existe. 🟡 Que la sala no tenga otra salida no se midió.

## Las posiciones (Chapter1_1.dat)

Leídas del mundo de LithTech: objetos `Marker` con `Name`, `Pos` (vector) y `Rotation` (3 ángulos en radianes;
los 8 «Player Start» en 0 = mirando a +z, hacia la puerta).

| marcador | x | y | z |
|---|---|---|---|
| Player Start 01 / 02 / 03 / 04 | 713.3 / 445.8 / 1248.2 / 1515.7 | −790.4 | −7482.5 |
| Player Start 05 / 06 / 07 / 08 | 1515.7 / 1248.2 / 713.3 / 445.8 | −790.4 | −7215.0 |

- Elegidos **04** y **08**: las dos esquinas opuestas de la grilla, a **1102.8 u** entre sí (en la misma sala:
  se ven). Distintos de 01 y 02, donde 🟡 probablemente aparecen los dos con `InitPlayGame`: así el teletransporte
  se nota.
- No se pueden poner mirándose: los 8 marcadores tienen la misma rotación (0) y `TeleportToMarker` no toma un
  ángulo. Se giran a mano.
- Los NPC del original más cercanos (`E_AP_01`/`02`, grupo 1) quedan a más de 3787 u y esta arena no los crea.
  `DoorM01` (el disparador de la puerta) está a 1588 u de `Player Start 04`.

## Medido (24-nov, sesiones 20261124-064128 y -064447)

- ✅ la dll 0.5.4 sirve el `.lua` suelto: `[traduccion] #6 (suelto) → data\scenario\easy\chapter1_1_e.lua`;
- ✅ **los dos clientes corren el guion**: cada uno manda sus `0x105C` (`PvP_Teleport`, `PvP_Cuenta`…) y los dos
  pasan por `SetEntityGroup` con la bandera de máster en 1;
- ✅ `GetPlayerID(0..4)` = `-1, 1, -1, 0, -1` (kai = entidad 1, rui = entidad 0): vacío = **−1**, y el **0 es un
  jugador**. `PvP_Jugadores` recorre 0..8 y descarta −1;
- ✅ `GetAlivePlayerNum` = 2 al empezar (`PvP_Vivos2`) y baja con la muerte de un jugador a manos del otro: el fin
  salió 5 s después de cada muerte (`OnEnd` → `0x1064` de los dos);
- ✅ el server acepta ese fin y paga el resultado **PvE** de 1011 (cartas): todavía no hay resultado PvP.

## Sin verificar

- `ShowTestMsg` en pantalla y `manager:GetHP` con un jugador (no se sacó foto durante la pelea);
- el teletransporte de rui (id 0): sólo se vio el `0x105C` del de kai (`Player Start 04` / `08`);
- que la sala de inicio no tenga otra salida.
