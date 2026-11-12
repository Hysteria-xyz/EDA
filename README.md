# EDA — Espada del Alma · servidor abierto

Servidor para **E.D.A. (Espada del Alma)**, el juego de acción por stages que **Softnyx**
(Gunbound, Rakion, WolfTeam) sacó en **closed beta en 2009** y que nunca llegó a lanzarse. Sus
servidores se apagaron hace años y el juego quedó como *lost media*.

Este repositorio lo revive: el server se escribió **desde cero en Python**, mirando qué manda el
cliente de 2009 y qué espera recibir. Con él el juego vuelve a andar: lista de servidores,
personajes, lobby, salas, stages completas, muerte y revivir, premios, tienda, inventario,
habilidades, refinería y multijugador.

## ¿Cuánto falta? — las piezas

Dos números **medidos sobre el exe del juego** (no escritos a mano): cuántos mensajes del server
sabe recibir el cliente de 2009 y cuántos ya le manda el nuestro, y cuántas de las llamadas a
Windows que escondió ASProtect ya están resueltas.

<!-- piezas: desde acá lo escribe herramientas/contar_piezas.py -->
| pieza | tenemos | avance |
|---|---|---|
| mensajes del server que el cliente sabe recibir | **46 / 62** | `███████████████░░░░░` 74 % |
| llamadas a Windows que ASProtect desvió, ya resueltas | **511 / 694** | `███████████████░░░░░` 74 % |

Faltan estos mensajes: `060B`, `1016`, `101A`, `1026`, `1030`, `1032`, `104B`, `1050`, `1056`, `105B`, `105D`, `1060`, `1062`, `1066`, `106D`, `3003`. Las llamadas que faltan no se tocan jugando (si el juego llega a una, la consola dice cuál).

<sub>Medido con `py herramientas\contar_piezas.py` sobre `EDA_limpio.exe` (md5 `0799387e23cadd355888bd712143f2d5`).</sub>
<!-- piezas: hasta acá -->

Qué anda pantalla por pantalla, y qué no: [LEEME.md](LEEME.md#qué-anda-hoy).

## Índice

| quiero… | ir a |
|---|---|
| **jugar en mi PC** (Windows, paso a paso desde cero) | [EMPEZAR.md](EMPEZAR.md) |
| **jugar en un server de otra PC** (un VPS) | [abajo](#jugar-en-un-server) |
| **abrir el EDA.exe ORIGINAL** (con ASProtect, saltando GameGuard) | [abajo](#el-exe-original-y-gameguard) |
| **montar el server en Linux** (Docker, VPS, prueba y prod) | [despliegue/LEEME.md](despliegue/LEEME.md) |
| **programar / mandar un PR** | [CONTRIBUIR.md](CONTRIBUIR.md) · el server por módulos: [servidor/LEEME.md](servidor/LEEME.md) |
| el protocolo, mensaje por mensaje | [documentacion/PROTOCOLO.md](documentacion/PROTOCOLO.md) |
| el registro de todo lo que se hizo, corrida por corrida | [documentacion/MEDICIONES.md](documentacion/MEDICIONES.md) |
| la historia del juego, con fuentes | [documentacion/HISTORIA.md](documentacion/HISTORIA.md) |
| aviso legal · licencia | [AVISO-LEGAL.md](AVISO-LEGAL.md) · [AGPL-3.0](LICENSE) |

## El cliente no está acá

Este repositorio tiene **sólo el servidor y las herramientas** (más `exe/EDA_limpio.exe`, ver
[exe/LEEME.md](exe/LEEME.md)). El cliente (`Data.dat`, los gráficos, la música) es de Softnyx y
**no se distribuye acá**. Necesitás tu propia copia del cliente de la beta de 2009; el `EDA.exe`
que conocemos tiene este md5:

```
f0b12e6cddf3efdd0676b6491efe46be   EDA.exe   (2.025.472 bytes, compilado el 2009-08-14)
```

[documentacion/INVENTARIO_CLIENTE_2009.md](documentacion/INVENTARIO_CLIENTE_2009.md) tiene el md5 de
cada archivo, para que compares tu copia.

## Jugar en tu PC

```bat
py -m pip install -r requirements.txt
py jugar.py --preparar "C:\ruta\al\cliente\de\EDA"
py jugar.py
```

**Windows**, con **Python 3.10 o más nuevo**. No hace falta ser administrador, y tu cliente no se
modifica (se juega desde una copia). `py jugar.py` levanta el server **en tu PC** y abre el juego.

⚠ No abras el juego con doble clic ni con el launcher de Softnyx: así sale **«Game guard
error»** y no encuentra el server. Siempre `py jugar.py`.

## Jugar en un server

Si alguien tiene el server andando en un VPS ([despliegue/LEEME.md](despliegue/LEEME.md)), con la
misma preparación de arriba:

```bat
py jugar.py --server IP_DEL_SERVER:25900
```

No se levanta nada en tu PC: el juego va directo a ese server. Los servers de la comunidad usan
**25900 = prod** (la rama `main`, estable) y **35900 = prueba** (la rama `develop`, lo último).

## El exe original y GameGuard

Hay dos formas de abrir el juego, y las dos **saltan GameGuard** (el anti-trampas de 2009, que
hoy corta el arranque buscando un server muerto):

| | qué abre | cómo salta GameGuard |
|---|---|---|
| `py jugar.py` (por defecto) | [`exe/EDA_limpio.exe`](exe/LEEME.md): el de 2009 **desempacado**, con los 4 parches ya escritos en el archivo | no hay nada que saltar: no trae GameGuard |
| `py jugar.py --original` | **tu `EDA.exe` de 2009 tal cual**, con su ASProtect | en **memoria**: Frida lo abre suspendido y, apenas ASProtect desempaca el código (~60 ms), escribe los 4 parches; el archivo no se toca |

Los 4 parches, qué hace cada uno, y cómo se los pone en memoria al original:
[LEEME.md → Cómo se abre el EDA.exe ORIGINAL](LEEME.md#cómo-se-abre-el-edaexe-original-el-que-tiene-asprotect).
Las dos formas funcionan con `--server`.

## Cómo está organizado

```
jugar.py          la entrada del jugador (Windows): prepara el juego, levanta el server, abre el cliente
servidor/         ★ EL SERVER, por módulos (tienda, salas, partida, refinería…): servidor/LEEME.md
  red.py          el server por la red: Linux, Docker o Windows
despliegue/       Docker y los scripts del VPS (prod y prueba): despliegue/LEEME.md
herramientas/     el resto: abrir el juego, el relay, y las de investigación (herramientas/LEEME.md)
exe/              EDA_limpio.exe (el de 2009 desempacado y sin GameGuard)
documentacion/    el protocolo, las mediciones, la historia
```

## Cómo se trabaja en equipo

- **`main`** = lo estable → el **server de prod**. **`develop`** = lo próximo → el **server de
  prueba**, que se actualiza solo a los 5 minutos de cada cambio.
- Los PR van **a `develop`**. Cada PR corre las pruebas solo (GitHub Actions): el server, el relay,
  el conteo de piezas y la imagen de Docker.
- Cuando `develop` anduvo bien en el server de prueba, se pasa a `main`.

Todo explicado en [CONTRIBUIR.md](CONTRIBUIR.md).
