# datos/ — las tablas del juego que lee el server

Cuatro XML que vienen **adentro de `Data.dat`** (el paquete del cliente de 2009), tal cual los
descomprime el juego:

| archivo | qué tiene | lo usa |
|---|---|---|
| `Product.xml` | la tienda: cada producto con su precio en oro y qué ítems da; lo que paga por cada ítem | `servidor/datos.py` → `tienda.py` |
| `Skill.xml` | las habilidades: clase, nivel para aprenderla, precio | `habilidades.py`, `pruebas.py` |
| `StageReward.xml` | el premio de cada stage (oro, EXP, ítems) | `partida.py` |
| `ItemTypeList.xml` | cada tipo de ítem: durabilidad máxima, precio de reparar, clase | `refineria.py` |

Están acá para que el server (en tu PC o en un VPS) ande completo sin pasos a mano. **Son de
Softnyx**, no nuestros, y no están bajo la AGPL: ver [AVISO-LEGAL.md](../AVISO-LEGAL.md).

Si el juego los saca de **tu** copia (`py jugar.py` los guarda en `_trabajo\datos\`), el server
usa esos. Si no, usa estos. Para cambiar de carpeta: `EDA_DATOS`.

Cómo se sacan de `Data.dat`: `herramientas/volcar_inflados.py` + `herramientas/sacar_xml.py`, o
solos al jugar (`herramientas/eda_original.py`).
