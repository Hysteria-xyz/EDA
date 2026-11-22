# La red de la partida (P2P) — para quien quiera trabajar en ella

> Corto, para arrancar. Lo medido en detalle está en `MEDICIONES.md` §47, §52 y §53, y el protocolo
> en `PROTOCOLO.md` §4.2–4.3 y §5.16.

## El síntoma: «-1000 ms» en la sala

En la sala de espera, al lado de cada jugador, sale su ping. **-1000 ms quiere decir que los dos juegos
no se están hablando por UDP.** Con -1000 la partida arranca, pero no se ven moverse.

## Cómo se hablan los juegos: tres caminos

La partida es **P2P** (de juego a juego, como en el original de 2009). El server sólo les dice a cada
uno «al otro lo encontrás en esta dirección» (mensaje `0x1059`). Elige el camino así
(`servidor/relay.py`, función `dir_udp`):

| camino | cuándo | ping medido |
|---|---|---|
| **casa** (IP privada) | los dos salen a internet por la misma IP | 33 ms (§52) |
| **directo** (IP pública) | los dos mandaron su dirección pública (el `0x3002`, `servidor/nat.py`) | 70–90 ms (§53) |
| **relay** (el VPS reenvía) | si no, o con `EDA_P2P=relay` | ~300 ms: el VPS está en Miami (§53) |

## Cómo cae al relay automáticamente (Plan B, 22-nov)

1. **Dirección del anfitrión siempre al día (`0x1057` con `+0x2DF = 2`):** en `EDA_limpio.exe`, `0x621980(4)` (que manda `0x3006` × 4 al puerto de punch del relay) sólo se llama desde dos sitios: `0x543802` al entrar como invitado (`0x1020`) y `0x54F0FC` en el anfitrión (y demás miembros) al recibir `0x1057` (`Someone_EnterRoom`) cuando el byte `+7` (`cuenta+0x2DF`) vale **`2`**. Ahora el server envía `+0x2DF = 2` en `0x1057`, por lo que también el anfitrión renueva su puerto UDP público cada vez que alguien entra a su sala. Además, antes de cada partida (`0x104E` → `0x104F`), el server verifica si cambió alguna dirección y reanuncia `0x1059` con la más reciente.
2. **Detección automática del `-1000 ms` desde el cliente de 2009 (`0x1059` con `+0x2DF = 3` → `0x105A`):** en `EDA_limpio.exe`, cuando el `0x1059` lleva `+0x2DF = 3` (`0x550D6B`), el cliente saluda por UDP durante 2 s (`0x74AA60`) y 1 s después (`0x535000` → `0x4DC330`) comprueba con `0x748120` si estableció conexión UDP con el anfitrión y le manda al server **`0x105A`** (`u32 id_cuenta · f32 fAveragePing · u8 byTimeOutCnt`). Si sigue en `-1000 ms` (`[UDP ERROR] PingError! PingInfo Not Collect!!!`), manda `byTimeOutCnt = 2` (`0x4DC453`). Al recibir `0x105A` con `timeouts >= 2`, el server marca a esa pareja como `sin_directo` y les reenvía de inmediato `0x1059` por el **relay** en ambos sentidos.
3. **Vencimiento de UDP viejo (`VENCE_PUBLICA = 300` s):** si la dirección pública de un jugador (`0x3002` o `0x3006`) lleva más de 5 minutos sin renovarse por UDP, ya no se reparte su puerto viejo: la pareja pasa al **relay**.
4. **En `EDA_P2P=auto`:** además, sólo se usa directo si ambos jugadores conservaron el mismo puerto entre su `0x3002` y su `0x3006` (`relay.estable`).

## Dónde está cada cosa

- `servidor/relay.py` → `dir_udp` (qué camino le toca a cada par) y `misma_casa`.
- `servidor/nat.py` → el `0x0607` / `0x0609` (la dirección pública de cada uno).
- `servidor/salas.py` → `pares()` arma el `0x1059` y anota en el registro qué camino le dio a cada uno.
- `herramientas/relay_udp.py` → el relay y el punch (corre en el VPS al lado del server).
- `herramientas/dll_d3d9/eda_d3d9.c` → `[p2p]`: la MAC y la IP privada.

## Cómo probar

- Hacen falta **dos PCs en casas distintas** (una puede estar con los datos del celular). Con dos juegos
  en la misma PC, o en la misma casa, no se ve este problema.
- Contra el **server de prueba** (puerto 35900, sin login; la dirección la pasa Rui):
  `py jugar.py --server DIRECCION:35900`, o el juego del launcher con `[red] server=` en `eda_d3d9.ini`.
- Qué mirar:
  · el ping de la sala (y el revés: con `EDA_P2P=relay` tiene que andar siempre, más lento);
  · el registro del server: «sala: a #N le doy #M por casa / directo / relay»;
  · `eda_d3d9.log` al lado del juego: las líneas `[p2p]`.
- Las pruebas del server: `py servidor\juego.py control` y `py herramientas\relay_udp.py control`.
  Una prueba nueva lleva **su caso al revés**, y en las pruebas van IPs de documentación (`192.0.2.x`,
  `198.51.100.x`, `203.0.113.x`), nunca la tuya.
- La PR va a **`develop`**: se prueba en el server de prueba antes de llegar a prod.
