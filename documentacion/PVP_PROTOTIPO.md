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

## 5 · El server árbitro del duelo (24-nov, experimental) — `servidor/duelo.py`

Sólo con **`EDA_PVP=1`** (`config.PVP`; `dos_clientes.py iniciar --pvp`). Sin la variable, el server no mira nada
de esto: lo prueba el primer caso de `pruebas_duelo` (un «PvP_*» no marca nada y el muerto recibe su `0x1068`).

| qué | cómo | prueba (`servidor/pruebas.py · pruebas_duelo`, con su revés) | en vivo |
|---|---|---|---|
| reconocer el duelo | el 1er `0x105C` tipo 0 de la partida cuyo nombre empieza con `PvP_` (los manda la arena) marca la sala; aviso por el chat «[Duelo] Duelo: rui vs kai» | ✅ (revés: `OnTrigger_01` no la marca) | ✅ sesiones `-072844`, `-074413`, `-074909`: «duelo rui #1 vs kai #3 (por «PvP_Teleport»)» |
| muerte → ganador | `0x1065` (`u8 jugador · u32 entidad que mató`): **sin** `0x1068` (no hay cuadro de revivir); el ganador es la conexión cuyo número de sala = esa entidad (medido: rui 0, kai 1, los NPC desde 256); si no calza, el otro del duelo. Aviso «Gana X (por KO)» y una línea en `duelos.jsonl` | ✅ (revés: una 2.ª muerte no cambia nada) | ⏳ falta un KO en vivo (ver abajo) |
| red de seguridad | el muerto queda con `game_over_en` a 25 s: si el guion no cierra la stage, sale el game over de siempre → lobby | ✅ | ⏳ |
| fin sin premio | `0x1064` en duelo: PlayEnd sin ítems, EXP y oro como estaban, cartas con 0 puntos y AWARD vacío (`[0, 0]`) a los 9,5 s → vuelve a la sala por el camino medido | ✅ | ⏳ |
| desconexión | gana el que queda (se anota con los dos nombres) | ✅ | ⏳ |

Lo que **no** hace: ranking, premios, sala de duelo propia. La pestaña Battle sigue cerrada.

### ⛔ Un error de la arena que encontró esta prueba (corregido)

Los **dos** clientes corren el guion, y cada uno arma la lista de jugadores en otro orden. Con
`SetEntityGroup(ids[2], 3)`, A cambió a rui (id 0) y B a kai (id 1): por la red se aplicaron los dos cambios y los
dos quedaron en `0x4` = **el mismo grupo otra vez** (sesión `-074413`, `entidades.jsonl`). La T05 del §0 anduvo
porque en ella A pidió un ID inválido (4294967295) y sólo valió el de B. Corregido: los IDs se ordenan y el menor va
explícitamente al grupo 1 y el mayor al 3, en los dos clientes. Medido en la sesión `-074909`: A y B piden
`SetEntityGroup(0, 1)` y `(1, 3)`, y los dos quedan con rui `0x1` y kai `0x4`.

### La automatización (por qué el KO en vivo sigue a mano)

- La dll 0.5.4 sólo deja pasar el teclado y el mouse «con EDA al frente» (`[mazino] entrada`): `iniciar --auto`
  lo apaga en las dos instalaciones de prueba y `combate_auto.py` trae la ventana al frente.
- `control_partida.py` necesita `_trabajo\entrada_formato.json` (el formato de entrada de LithTech: `control_partida.py
  lanzar`); sin él, lo inyectado va con offsets equivocados.
- Con eso kai se mueve, pero la mayoría de las órdenes se pierden y acertarle al otro a ciegas no es confiable:
  en 30 rondas automáticas no hubo ningún golpe (ni un `OnDamaged`). La pelea la tiene que hacer una persona.

**Para probarlo a mano:**
```bat
py herramientas\pvp\dos_clientes.py recursos instalar --grupos
py herramientas\pvp\dos_clientes.py iniciar --pvp --hex
py herramientas\pvp\dos_clientes.py llevar partida
```
Pelear hasta que uno muera. Qué tiene que pasar: el muerto **no** ve el cuadro de revivir; en el chat sale
«[Duelo] Gana …»; a los ~5 s la stage termina, el resultado y las cartas sin puntos, el AWARD en 0 y la vuelta a la
sala. `server.log` tiene la línea `[duelo] … gana …` y `EDA_pvp\estado\duelos.jsonl` el registro.

## 6 · Lo siguiente

1. Encontrar el test de grupos del golpe cuerpo a cuerpo (con `entidades.py` + un punto nuevo).
2. ✅ (código y pruebas; ⏳ el KO en vivo) Server árbitro del duelo: §5.
3. Elegir el escenario de la arena sin pisar la 1011 de nadie: un canal propio de la dll (PVP_ARQUITECTURA.md §1)
   en lugar de `traducciones\es\`.
4. La pestaña Battle sigue sin habilitarse (PVP_BATTLE_UI.md).
