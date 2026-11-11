# Aviso legal

Vale la pena ser claro sobre qué es de quién, porque la diferencia importa.

## Qué es nuestro

El **servidor** (`servidor/`), el lanzador (`jugar.py`), las **herramientas** (`herramientas/`) y
toda la **documentación** (`documentacion/`).

El server se escribió desde cero: se miró qué mensajes manda el cliente y qué espera recibir, y se
escribió un programa que conteste eso. **No hay código de Softnyx adentro**, ni descompilado ni
copiado. La documentación cita direcciones y unos pocos bytes del ejecutable (para explicar qué se
midió y dónde), que es lo que hace falta para que un programa nuevo pueda hablar con el viejo.

Eso es lo único que licenciamos, y va bajo [AGPL-3.0](LICENSE).

## Qué no es nuestro

Todo el juego:

- el cliente y sus ejecutables (`EDA.exe`, las `.dll`, el launcher y el patcher)
- `Data.dat` y todo lo que tiene adentro: los mapas, los modelos, la música, los gráficos, los
  guiones de las stages y las tablas (ítems, tienda, habilidades, premios)
- GameGuard (de nProtect)

Nada de eso está en este repositorio, ni lo va a estar. Pertenece a **Softnyx Co., Ltd.** (y
GameGuard a INCA Internet).

Por eso las tablas que el server necesita (`Product.xml`, `Skill.xml`, `StageReward.xml`,
`ItemTypeList.xml`) **no vienen acá**: `herramientas/eda_original.py` las guarda **de tu propia
copia del juego** la primera vez que el juego las abre. Nadie te está dando nada que no tuvieras ya.

## El juego original no se modifica

`py jugar.py --original` abre el `EDA.exe` de 2009 tal cual. Lo que hace falta cambiar (saltear GameGuard,
que busca un server que ya no existe, y llevar la conexión a tu PC) se hace **en memoria**,
mientras corre, y se pierde al cerrarlo.

## La única excepción: `exe/EDA_limpio.exe`

En algunas PCs GameGuard alcanzaba a arrancar antes que los cambios en memoria («Game guard
error : 45»). Por eso `py jugar.py` usa por defecto **el único** ejecutable que incluye el repositorio: `exe/EDA_limpio.exe`, el `EDA.exe`
de Softnyx **desempacado y sin GameGuard** (cómo se armó: [exe/LEEME.md](exe/LEEME.md)). **No es
nuestro**: es su programa de 2009 con esos cambios, publicado sólo para preservar un juego que
nunca salió de beta. No sirve solo (hace falta tu propio cliente, con `Data.dat`) y no está bajo
la AGPL. Si Softnyx pide sacarlo, se saca.

## Este proyecto no cobra

Nunca. Ni ítems, ni VIP, ni ventajas pagas. Es un proyecto de preservación de un juego que nunca
salió de beta y cuyos servidores llevan años apagados.

Si levantás tu propio servidor con este código, la AGPL te lo permite, incluso cobrar. Pero
entonces tus jugadores tienen derecho a tu código.

## Si sos de Softnyx

Abrí un issue en el repositorio y lo hablamos. No hay ninguna intención de competir con nada de
ustedes: este juego nunca llegó a lanzarse y sus servidores no existen desde hace más de una década.
