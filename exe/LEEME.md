# EDA_limpio.exe

```
d1889597cfa734e7a44a5db742589d01   EDA_limpio.exe   (6.139.904 bytes)
```

Es el `EDA.exe` de 2009 (md5 `f0b12e6cddf3efdd0676b6491efe46be`) **desempacado** (sin
ASProtect) y **sin GameGuard**. Es el que abre `py jugar.py` por defecto: en algunas PCs el
original, ajustado en memoria, mostraba **«Game guard error : 45»** (GameGuard alcanzaba a arrancar
antes que los parches). Éste ya los trae en el archivo. El original sigue con `--original`.

```bat
py jugar.py              (éste)
py jugar.py --original   (el EDA.exe de 2009, con ASProtect)
```

(`--preparar` lo copia a `_trabajo\juego\` junto con el resto del juego. Necesita **tu** cliente
de 2009 igual: este exe solo no alcanza, le falta `Data.dat` y todo lo demás.)

## Cómo se armó

Con las herramientas de este repositorio, sobre una copia del cliente de 2009:

1. `volcar_exe.py` — el exe desempacado, tomado de la memoria mientras el juego corre.
2. `emular_stub.py`, `robados.py`, `juntar_apis.py` (+ `documentacion/APIS_A_MANO.md`) — a qué
   función de Windows iba cada una de las llamadas que ASProtect había desviado (510 de 694
   resueltas; las demás llevan una «trampa» que dice cuál se alcanzó si el juego llega ahí).
3. `desempacar.py construir` — rearma el exe: imports, código robado
   (`documentacion/CODIGO_ROBADO.md`), datos iniciales.
4. `sin_gameguard.py limpio` — los 4 cambios (12 bytes): `0x7CE890` (NPGameLib no se crea),
   `0x403606` (el juez de GameGuard no se llama), `0x402EC4` y `0x402EFB` (el chequeo de cada
   10 s —GameGuard y que el render sea «d3d9.dll»— no cierra el juego).

Todo eso está contado paso a paso en `documentacion/MEDICIONES.md` (corridas 13 a 16).

## ⚠ No es nuestro

El programa es de **Softnyx**: esto es su ejecutable de 2009 con esos cambios, publicado para
preservar un juego que nunca salió de beta. Ver [AVISO-LEGAL.md](../AVISO-LEGAL.md). Si Softnyx
pide sacarlo, se saca.
