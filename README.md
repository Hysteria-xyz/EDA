# EDA — Espada del Alma · servidor abierto

Servidor para **E.D.A. (Espada del Alma)**, el juego de acción por stages que **Softnyx**
(Gunbound, Rakion, WolfTeam) sacó en **closed beta en 2009** y que nunca llegó a lanzarse. Sus
servidores se apagaron hace años y el juego quedó como *lost media*.

Este repositorio lo revive: el server se escribió **desde cero en Python**, mirando qué manda el
cliente de 2009 y qué espera recibir. Con él el juego vuelve a andar en tu PC: lista de
servidores, personajes, lobby, salas, stages completas, muerte y revivir, premios, tienda,
inventario, habilidades, refinería y multijugador.

- **Paso a paso desde cero (Windows):** [EMPEZAR.md](EMPEZAR.md)
- **Qué anda, qué no y cómo está hecho:** [LEEME.md](LEEME.md)
- **El protocolo, mensaje por mensaje:** [documentacion/PROTOCOLO.md](documentacion/PROTOCOLO.md)
- **El registro de todo lo que hicimos, corrida por corrida:** [documentacion/MEDICIONES.md](documentacion/MEDICIONES.md)
- **La historia del juego, con fuentes:** [documentacion/HISTORIA.md](documentacion/HISTORIA.md)
- **Aviso legal:** [AVISO-LEGAL.md](AVISO-LEGAL.md)
- **Licencia:** [AGPL-3.0](LICENSE)

## El cliente no está acá

Este repositorio tiene **sólo el servidor y las herramientas**. El cliente (`EDA.exe`, `Data.dat`,
los gráficos, la música) es de Softnyx y **no se distribuye acá**. Necesitás tu propia copia del
cliente de la beta de 2009; el `EDA.exe` que conocemos tiene este md5:

```
f0b12e6cddf3efdd0676b6491efe46be   EDA.exe   (2.025.472 bytes, compilado el 2009-08-14)
```

[documentacion/INVENTARIO_CLIENTE_2009.md](documentacion/INVENTARIO_CLIENTE_2009.md) tiene el md5 de
cada archivo, para que compares tu copia.

## Resumen rápido

```bat
py -m pip install -r requirements.txt
py jugar.py --preparar "C:\ruta\al\cliente\de\EDA"
py jugar.py
```

**Sólo Windows**, con **Python 3.10 o más nuevo**. No hace falta ser administrador, y el juego
original no se modifica: el exe de 2009 (con su ASProtect) se abre tal cual y los cambios se
hacen en memoria (`herramientas/eda_original.py`).

Si en tu PC el juego dice **«Game guard error»**, usá el exe ya desempacado y sin GameGuard que
viene en [exe/](exe/LEEME.md):

```bat
py jugar.py --limpio
```
