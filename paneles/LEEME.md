# Paneles (las ventanas que el cliente de 2009 no trae)

Ventanas aparte, al estilo de EDA, que corren en **la misma PC que el server local** (`jugar.py`) y
hablan con él por archivos de `_trabajo/servidor/` (no por la red). Sólo Windows (tkinter + ctypes).

| archivo | qué hace |
|---|---|
| **`EDA-Messenger.py`** | el MESSENGER: lista de amigos (conectado / dónde está) y una ventana de conversación por amigo. Los mensajes a un desconectado quedan guardados y los lee al volver. Lo abre y lo cierra el botón Messenger del lobby o **F11** |
| **`EDA-Opciones.py`** | las OPTIONS (resolución, ventana, brillo, sonido…) al estilo del juego. Con el juego abierto por `eda_original.py` se aplican **al instante** (la consola del juego, `RunConsoleString`); además quedan en `autoexec.cfg`. Lo abre el botón Options o **F10** |
| **`EDA-Teclas.py`** | el panel de TECLAS: F1–F8, pociones, WASD, mouse, cambio de arma… Se aplican **en vivo** (`Bind` de la consola) y quedan en `autoexec.cfg` |
| **`EDA-Atajos.py`** | F10 Options · F11 Messenger · F12 Clan (reservado), sólo con EDA al frente. Lo abre el server local al entrar al lobby; se cierra solo cuando no queda EDA abierto |
| **`eda_ui.py`** | el kit de dibujo compartido (ventana, botones, pestañas, deslizadores al estilo EDA) |

## Dónde van

Los paneles esperan estar **al lado de la carpeta del repo** (como los deja una instalación de
jugador):

```
EDA\                  ← la carpeta del juego
├── EDA-Messenger.py  ← copiados de repo\paneles\
├── EDA-Opciones.py
├── EDA-Teclas.py
├── EDA-Atajos.py
├── eda_ui.py
└── repo\             ← este repositorio (server, herramientas, _trabajo\)
```

El server (`servidor/messenger.py`) los busca ahí (`os.path.dirname(config.RAIZ)`): si no están, los
botones del lobby contestan sólo en el chat. Lo que eligen los paneles queda en
`EDA-opciones.json` / `EDA-teclas.json` al lado de ellos, y `herramientas/eda_original.py` lo manda
al juego en vivo.

## Pruebas

```
python EDA-Messenger.py --prueba
python EDA-Opciones.py --prueba
python EDA-Teclas.py --prueba
```
