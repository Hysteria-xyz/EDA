# EDA — guía del proyecto

## Qué anda hoy

Probado con el cliente de 2009, pantalla por pantalla (cada cosa tiene su medición en
[documentacion/MEDICIONES.md](documentacion/MEDICIONES.md)):

| | |
|---|---|
| ✅ arranque | GameGuard pasado (en memoria), lista de servidores, anuncio |
| ✅ personajes | crear (Warrior / Hunter), elegir, entrar al lobby |
| ✅ lobby | lista de salas, lista de usuarios, chat, Select Character, botones |
| ✅ salas | crear, entrar, listo / F9, chat de sala, hasta 3 jugadores |
| ✅ stages | carga, largada, el combate (corre en el cliente), muerte, **revivir con moneda**, game over, salir |
| ✅ fin de stage | resultado con rango, **cartas** (oro / plata / bronce), premios de `StageReward.xml` |
| ✅ progreso | EXP y niveles (tabla de `Player.xml`), progresión de stages, **puntos de estadística** |
| ✅ inventario | equipar (clic derecho), barra de pociones (teclas 1–6), todo guardado en la cuenta |
| ✅ tienda | comprar, **Purchase All**, vender (precios de `Product.xml`) |
| ✅ habilidades | verificar el libro con el pergamino, aprender (con oro y nivel), borrar, barra F1–F8 |
| ✅ refinería | crear engarce, poner piedras (suman su bonus), refinar piedras, reparar |
| ✅ multijugador | P2P en la misma PC (ping y movimiento); *relay* UDP para PCs distintas (probado en una PC) |

## Qué NO anda (todavía)

- ⛔ **Lanzar las habilidades jugando.** F1–F8 marcan la habilidad en la barra, pero no se dispara
  (ni en el exe original). Es algo que el server no le manda y no se encontró qué. Lo descartado
  está en MEDICIONES §34.
- 🟡 La durabilidad no baja jugando; el oro que da una stage es inventado; los puntos por nivel
  (3) y los lugares de habilidad (12) son nuestros: los de 2009 no se saben.
- 🟡 El relay entre dos PCs de verdad no se probó.

Todo lo que es deducción y no medición está marcado 🟡 en el código y en la documentación.

## Cómo está hecho

```
jugar.py                 la entrada: prepara el juego, levanta el server y abre el cliente
                         (`--server IP:PUERTO` = jugar contra un server de otra PC)
servidor/                ★ EL SERVER DE JUEGO, por módulos (servidor/LEEME.md): cuentas, salas,
                         partida, tienda, inventario, habilidades, refinería…
  juego.py               la entrada: a qué módulo le toca cada mensaje
                         (`py servidor\juego.py control` = sus pruebas, con su caso al revés)
  red.py                 el server por la red, para Linux / Docker / un VPS
despliegue/              Docker y los scripts del VPS: prod (main) y prueba (develop)
herramientas/            el resto: ver herramientas/LEEME.md
  espiar_broker.py       el oyente TCP de Windows (el de jugar.py): descifra cada paquete y se lo
                         pasa a servidor/
  contar_piezas.py       ★ cuántos mensajes y llamadas faltan, medido sobre el exe (la tabla del README)
  paquete_broker.py      el formato y el cifrado de la red (AES-128 con la clave = MD5 del exe)
  reglas_broker.py       las respuestas fijas del Broker (anuncio, lista de servidores)
  eda_original.py        abre el EDA.exe de 2009 y lo ajusta en memoria (GameGuard, red, datos)
  relay_udp.py           el relay del multijugador entre PCs
  …                      y las de investigación: desempacar el exe, mirar la red, controlar el juego
documentacion/
  PROTOCOLO.md           ★ cada mensaje, con su formato y quién lo maneja en el exe
  MEDICIONES.md          ★ el registro: qué se probó, qué salió, en orden (36 corridas)
  HISTORIA.md            qué fue EDA, con fuentes
  INVENTARIO_CLIENTE_2009.md   el md5 de cada archivo del cliente
  APIS_A_MANO.md / CODIGO_ROBADO.md   lo que se resolvió a mano para desempacar el exe
  SIGUIENTE_PASO_RED.md  la hoja de ruta de la red (histórica)
```

## Cómo se abre el EDA.exe ORIGINAL (el que tiene ASProtect)

Es lo que hace `py jugar.py --original` (`herramientas/eda_original.py`); sin tocar el archivo:

1. Se lanza `EDA.exe` **suspendido** con Frida (`frida.spawn`) desde `_trabajo\juego\` y se le
   inyecta un script antes de que corra una sola instrucción.
2. El script engancha `ws2_32!connect`: la conexión a `218.145.66.187:25000` (el Broker de 2009,
   que sale de un XML adentro de `Data.dat`) va a `127.0.0.1:25900`, nuestro server.
3. El juego arranca. ASProtect desempaca el código **en memoria**; un reloj de 2 ms mira las
   cuatro direcciones y, **apenas tienen sus bytes originales** (ya desempacadas, todavía sin
   correr), les escribe los parches de `sin_gameguard.py limpio` (también se intenta desde
   `GetCommandLineA` y `SetWindowLongA`, pero ASProtect emula esas funciones y no llegan):

   | dirección | antes | después | qué hace |
   |---|---|---|---|
   | `0x7CE890` | `a1 30 9e 94 00` | `33 c0 c3 90 90` | el init de NPGameLib devuelve 0: GameGuard no se crea ni se lanza |
   | `0x403606` | `e8 a5 f5 ff ff` | `b0 01 90 90 90` | el «juez» de GameGuard no se llama (`mov al, 1`) |
   | `0x402EC4` | `74 0c` | `eb 0c` | el chequeo de GameGuard de cada 10 s no cierra el juego |
   | `0x402EFB` | `74 0c` | `eb 0c` | el otro chequeo de cada 10 s («d3ddevice» = «d3d9.dll») tampoco: bajo Frida a veces fallaba y el juego se cerraba solo a los 10 s |

   Medido: los cuatro entran a los ~60 ms. Si un byte no es el esperado, **no se escribe** (y avisa).
4. Cuando `inflate` (zlib, `0x788260`) ya está desempacado, se engancha para guardar en
   `_trabajo\datos\` los 4 XML que lee el server, la primera vez que el juego los descomprime.

El cifrado de la red usa como clave el **MD5 del exe que habla** (`paquete_broker.py`): el
server la calcula sola de los exes que hay en `_trabajo\juego\`, sea el original o el limpio, y
además trae fijas las de los dos exes conocidos (`CLAVES_FIJAS`), así un server en Linux, sin
ningún exe, los entiende igual.

Por defecto `py jugar.py` no usa el original sino `exe/EDA_limpio.exe`, que ya trae todo eso en
el archivo ([exe/LEEME.md](exe/LEEME.md)): con la versión anterior (sólo el reloj) en algunas
PCs GameGuard ganaba la carrera («Game guard error : 45»).

## El recorrido, en corto

1. **El exe venía empaquetado con ASProtect** (sin texto legible, 694 llamadas a Windows desviadas a
   una máquina virtual). Se volcó de la memoria y se rearmó un exe desempacado
   (`volcar_exe.py`, `desempacar.py`, `emular_stub.py`…): el motor es **LithTech**.
2. **GameGuard** cortaba el arranque buscando un server de actualización muerto: un `if` en
   `0x403606`, el init de NPGameLib y un chequeo cada 10 s (`sin_gameguard.py`).
3. **El Broker** estaba en `218.145.66.187:25000`, escondido en un XML comprimido dentro de
   `Data.dat`. Su protocolo: **AES-128-ECB** con una magia por bloque, y la clave = **MD5 del
   propio exe** (un control de integridad).
4. Con eso se escribió el server mensaje por mensaje: cada respuesta se dedujo leyendo el
   manejador del cliente en el exe y se comprobó en pantalla, con un **control al revés** (el caso
   que tiene que fallar). Así se llegó al lobby, a la partida, al final de la stage y a todo lo demás.
5. **El juego se maneja solo** para probar sin manos: clics por mensajes de ventana
   (`clic_juego.py`), teclado y mouse inyectados en el DirectInput del juego (`control_partida.py`,
   Frida) y un piloto que va del arranque a la partida (`piloto.py`, `multi.py`).
6. Al final, **el exe original** pasó a abrirse directamente con los ajustes en memoria
   (`eda_original.py`), sin repartir ningún exe modificado.

## Reglas con las que se trabajó

- **Medir antes que deducir.** Un desensamblado dice cómo se lee un dato, casi nunca quién lo
  escribe. Si la primera hipótesis se cae: gancho y a medir.
- **Toda prueba lleva su control al revés**, y lo esperado sale del generador (los XML del juego),
  no se escribe a mano.
- **Nada se afirma sin fuente**; lo deducido se marca 🟡.
- **El cliente original no se toca**: se juega desde una copia, y los cambios van en memoria.
