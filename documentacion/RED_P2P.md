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

## El problema que falta resolver ⏭

**El directo a veces no conecta, y entonces queda en -1000.** Pasó en prod: el registro del server
decía «sala: a #1 le doy #2 por directo (pública)» y al revés, y el ping estaba en -1000. Antes de prender
el directo, la misma situación andaba por el relay (con ~300 ms).

La causa más probable (🟡 sin medir todavía): **un NAT «simétrico»**. Hay routers (muchos de celulares y
algunos de fibra) que le cambian el PUERTO de salida según a quién le hablás. Entonces el puerto que
vio el server (por el `0x3002`) no es el que va a usar ese jugador para hablarle al otro, y el saludo
(`0xC354`) nunca entra.

**Lo que hay que hacer:** que cuando el directo no conecta, ese par se pase **solo** al relay. Ideas, de
la más simple a la más fina (hay que medir cuál anda):

1. **Detectar el NAT simétrico antes:** que el juego mande su `0x3002` a DOS puertos distintos del relay.
   Si el server ve dos puertos públicos distintos, ese jugador es simétrico → el server le da el relay
   (a él y a sus pares). Es lo que hacían los juegos de la época, y el mensaje `0x3003` del original
   («NAT type sort») parece ser justo eso: mirar qué hace el cliente con él.
2. **Volver a mandar el `0x1059`:** si a los N segundos la sala sigue en -1000, el server manda otro
   `0x1059` con el relay. Primero hay que medir si el cliente acepta un segundo `0x1059` con la sala abierta.
3. **Desde la dll** (`herramientas/dll_d3d9/eda_d3d9.c`, bloque `[p2p]`): si en X segundos no llega
   nada del otro jugador, usar el relay.

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
