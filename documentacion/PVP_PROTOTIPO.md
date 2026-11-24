# PvP — Fase 1: el prototipo experimental de combate

> Rama `feature/pvp-system`. Fuentes: [PVP_SETENTITYGROUP.md](PVP_SETENTITYGROUP.md) (el filtro de grupos),
> [PVP_ARQUITECTURA.md](PVP_ARQUITECTURA.md) (la arena), [PVP_MEDICIONES.md](PVP_MEDICIONES.md) (las sesiones).
> Todo local: server propio en 127.0.0.1:27900, dos clientes en `%USERPROFILE%\EDA_pvp\A` y `\B`.
> ✅ medido · 🟡 indicio · ⏳ falta · ❌ medido que no.

## 0 · Lo que ya se sabe (24-nov)

**Con los dos jugadores en grupos distintos, el combate entre jugadores anda de forma nativa, sincronizado en los
dos clientes, con muerte y con el atacante informado al server.** Medido con dos clientes reales manejados por una
persona (sesión `20261124-064447`):

```
06:46:16  SetEntityGroup(1, 3) en los dos clientes → SetGroup: entidad 1 (kai), máscara 0x4   (rui sigue en 0x1)
06:46:57  rui → kai   15.6   kai 84.6 → 68.98   (OnDamaged en A y en B; A recibe la vida de kai por red)
06:47:04  kai → rui   22.2   rui 84.6 → 62.40
   …      9 golpes en total, en los dos sentidos, de 15 a 22 cada uno
06:48:28  rui → kai   21.4   kai → 0 → «muerte» → server: 0x1065 = 01 · 00000000 (murió 1, lo mató la entidad 0)
06:48:33  los dos mandan 0x1064 (el guion: vivos 2 → 1 → OnEnd)
06:48:48  kai: «Confirmar» → 0x106A → 0x106B (revive con moneda) → vida 84.6 en los dos
```

✅ **El control negativo (T01) también está hecho**, a mano, con la misma arena pero **sin** `SetEntityGroup`
(sesión `20261124-070421`): más de 10 golpes de cada lado, pegados, y **ni un punto de daño**: sin reacción al golpe,
barras llenas en los dos, cero `OnDamaged`. Lo único que cambia entre las dos corridas es la máscara de grupo ⇒
**la máscara de grupo (`entidad+0x40`) es lo que decide si un jugador puede dañar a otro.**

## 1 · Las piezas

| pieza | qué hace | dónde |
|---|---|---|
| dos clientes | instalaciones aisladas, dll 0.5.4 verificada, server propio, cuentas rui / kai, recursos experimentales sólo ahí | `herramientas/pvp/dos_clientes.py` |
| arena | guion Lua servido en memoria por la dll en lugar de `data\scenario\easy\chapter1_1_e.lua` (stage 1011): sin NPC, teletransporte, cuenta regresiva, `SetEntityGroup` (con `--grupos`), vigilancia de vivos, fin | `herramientas/pvp/arena/` (LEEME.md) |
| entidades | Frida, sólo lectura, 10 puntos del exe verificados por bytes: grupos, filtros, `OnDamaged` (víctima, atacante, daño), vida, muerte, revivir | `herramientas/pvp/entidades.py` |
| combate_auto | una acción con marca horaria + la barra de HP de los dos antes y después, con foto | `herramientas/pvp/combate_auto.py` |
| udp_combate | todo el UDP de la partida, entero, con marcas | `herramientas/pvp/udp_combate.py` |
| vida | buscar / mirar un valor en memoria | `herramientas/pvp/vida.py` |
| server | `server.log` con `--hex`: cada `0x105C` del guion (`PvP_*`), `0x1065` (muerte + atacante), `0x1064`, `0x106A` | `dos_clientes.py iniciar --hex` |

## 2 · Las pruebas

| | prueba | esperado | real | evidencia | conclusión |
|---|---|---|---|---|---|
| T01 | ataque normal contra otro jugador, **sin** cambios | si el filtro de grupos es la causa: ningún daño | ✅ **sin daño** | sesión `-070421` (la arena SIN grupos, **a mano**, más de 10 golpes de cada lado, pegados): sin reacción al golpe ni vida que baje (lo vio el tester), barras 221 / 221, **cero** `OnDamaged`, cero `0x1063` y cero `0x1065` en el server. Antes, `-062450` (stage original, automático): lo mismo | con el mismo grupo los jugadores no se dañan; con grupos distintos sí (T05): **la máscara de grupo es lo que habilita el PvP** |
| T02 | habilidad de área cerca de otro jugador | — | 🚫 | las habilidades no se lanzan en la partida, tampoco con el exe original (MEDICIONES §34) | bloqueado por otra cosa; el filtro de área (`0x5596CA`) existe y es el mismo test de grupos |
| T03 | colisión entre jugadores | — | 🟡 no chocan | kai caminó 3 s contra rui: superpuestos en las dos pantallas (`03_choque_despues_A/B.png`) | los jugadores se atraviesan; limita el cuerpo a cuerpo, no lo impide |
| T04 | `SetEntityGroup` con firma verificada | el grupo cambia en los dos clientes | ✅ | `SetEntityGroup(1, 3)` → `SetGroup` id 1 → máscara `0x4` en A **y** en B; el paquete `1b000000 01000000 03000000` pasó por el server como `0x105C`/`0x105D` | la función hace lo que dice el análisis estático, y se sincroniza |
| T05 | ataque después del cambio de grupo | daño | ✅ | 9 golpes en los dos sentidos (tabla §0) | hay combate entre jugadores |
| T06 | daño y sincronización en los dos clientes | la misma vida en los dos | ✅ | cada golpe: `OnDamaged` en A y en B con la misma víctima, atacante y daño; `vida_red` en el otro cliente con el mismo valor | el motor ya sincroniza el combate P2P |
| T07 | muerte y lo que recibe el server | `0x1065` | ✅ | `0x1065` = `u8 jugador · u32 atacante` (PROTOCOLO §5.11 lo daba como 🟡 «0x108 = quién lo mató»): ahora medido con dos jugadores | el server puede saber quién ganó sin tocar el cliente |
| T08 | vuelta al lobby y el PvE sigue | el PvE igual | ✅ | sesión `-070959`: `recursos quitar` → 0 archivos sueltos servidos; corre el guion ORIGINAL (`Briefing_01`, `OnTrigger_01`, `DoorL01`, `NpcGroup01`…); a mano: 37 golpes de jugadores a 10 monstruos (grupo 2) y 7–8 de monstruos a jugadores, en los dos clientes; 10 monstruos muertos (`[bajas] 10/78` en el server); 2 muertes de jugador por monstruos y 2 revividas; **0 golpes entre jugadores** | quitar la arena devuelve el juego al PvE de siempre; el PvP sólo existe donde el guion cambia el grupo |

### Lo que el diagnóstico NO vio (y hay que entender)

- Los golpes cuerpo a cuerpo entre jugadores **no pasaron por ninguno de los tres filtros enganchados**
  (`0x554B70` golpe por red, `0x5596CA` área, `0x55758A` agarre), ni con grupos iguales ni distintos. El test de
  grupos que decide el golpe cuerpo a cuerpo está en otra función: falta encontrarla (entre los «varios más» de
  PVP_SETENTITYGROUP.md §5). En cambio, en el PvE (T08) el filtro de **área** `0x5596CA` se llamó ~800 veces:
  🟡 los ataques de los monstruos pasan por ahí.
- 🟡 **Los dos clientes corren el guion** y los dos piden `SetEntityGroup` con la bandera de máster en 1: el grupo se
  aplica dos veces (una local y una por red). No hizo daño, pero el día que los dos pidan cosas distintas no está
  claro cuál gana.

## 3 · Lo que falta, con tus manos

Todo con: `py herramientas\pvp\dos_clientes.py cerrar` entre una prueba y otra. El diagnóstico va en otra consola:
`py herramientas\pvp\entidades.py mirar 300` (arrancarlo apenas los dos estén en la stage).

**Paso A — T01, el control negativo:** ✅ hecho el 24-nov (sesión `20261124-070421`). Para repetirlo:
```bat
py herramientas\pvp\dos_clientes.py recursos instalar          :: la arena SIN grupos
py herramientas\pvp\dos_clientes.py iniciar --hex
py herramientas\pvp\dos_clientes.py llevar partida
```
Con los dos personajes pegados, **exactamente como en la prueba que hiciste**: 10 golpes de rui a kai y 10 de kai a
rui. Decime: ¿se vio la animación del golpe? ¿alguno hizo la animación de recibir el golpe? ¿bajó alguna barra?
Si no baja ninguna y en la consola de `entidades.py` no sale ningún `OnDamaged` → **el grupo es la llave**.

**Paso B — repetir T05 a propósito** (`recursos instalar --grupos`, lo mismo): una pelea hasta que uno muera, y
anotá quién ganó. Así T05 queda con la prueba registrada desde el principio.

**Paso C — T08:** ✅ hecho el 24-nov (sesión `20261124-070959`). Para repetirlo: después de las cartas, Confirmar → sala → salir al lobby. Entonces
`py herramientas\pvp\dos_clientes.py recursos quitar`, `cerrar`, `iniciar`, `llevar partida` y jugá la stage
normal (que salgan los monstruos y les puedas pegar). Decime si algo se ve distinto de siempre.

Pasame la carpeta de cada sesión (`EDA_pvp\registros\<hora>`).

## 4 · Decisión de arquitectura (T01 y T05 hechos)

**Arquitectura A, con una extensión mínima que ya existe.** El combate entre jugadores lo hace el motor original,
P2P y sincronizado; lo único que hace falta es que los dos jugadores **no compartan grupo**, y eso lo hace una
función del propio juego (`SetEntityGroup`) llamada desde un guion de escenario, que la `d3d9.dll` actual ya sabe
servir sin tocar `Data.dat` ni el exe. El server arbitra con lo que ya recibe: el `0x1065` dice quién murió y
quién lo mató.

- No hace falta la arquitectura B (reportes de golpes desde la dll) para un duelo; queda para validar daño
  (antitrampas) más adelante.
- C (combate calculado en el server) no se justifica: el motor ya lo resuelve y lo sincroniza.

Riesgos abiertos: el filtro cuerpo a cuerpo sin identificar; los dos clientes corriendo el guion; la arena paga hoy
el resultado PvE (el server tiene que distinguir la partida PvP antes del ranking — que no se implementa todavía);
el guion experimental reemplaza la stage 1011 Easy **sólo** en `EDA_pvp\A` y `\B`.

## 5 · Lo siguiente

1. Encontrar el test de grupos del golpe cuerpo a cuerpo (con `entidades.py` + un punto nuevo).
2. Server: reconocer la partida de duelo (la arena manda `PvP_*` por `0x105C`) y, en ella, usar el `0x1065` para
   declarar ganador en lugar del cuadro de revivir; sin premio ni ranking todavía.
3. Elegir el escenario de la arena sin pisar la 1011 de nadie: un canal propio de la dll (PVP_ARQUITECTURA.md §1)
   en lugar de `traducciones\es\`.
4. La pestaña Battle sigue sin habilitarse (PVP_BATTLE_UI.md).
