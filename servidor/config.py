r"""servidor/config.py -- DÓNDE vive cada cosa y en qué puertos escucha el server.

Todo sale de variables de entorno (las usa Docker, `despliegue/`) con un valor por defecto que es
el de siempre en Windows (`_trabajo/…`). El resto del server lee estos nombres como `config.X` en
el momento de usarlos (no los copia), así las pruebas los cambian en caliente.

    EDA_ESTADO      dónde se guardan las cuentas y lo del relay     (_trabajo/servidor)
    EDA_DATOS       los XML del juego que lee el server             (_trabajo/datos, o datos/)
    EDA_RELAY_IP    la IP PÚBLICA del server: prende el relay UDP   (sin ella: archivo modo_relay)
    EDA_RELAY_BASE  el 1er puerto UDP del relay                     (26000)
    EDA_PUNCH_PUERTO el puerto UDP de punch sin relay               (25001)
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import paquete_broker as P                                   # noqa: E402,F401

ESTADO = os.environ.get("EDA_ESTADO") or os.path.join(RAIZ, "_trabajo", "servidor")

def _datos():
    """Los XML del juego: EDA_DATOS si está; si no, los que guardó TU juego (`_trabajo/datos`, los
    escribe `eda_original.py`); si no, los que trae el repositorio (`datos/`)."""
    if os.environ.get("EDA_DATOS"):
        return os.environ["EDA_DATOS"]
    propios = os.path.join(RAIZ, "_trabajo", "datos")
    return propios if os.path.exists(os.path.join(propios, "Product.xml")) else os.path.join(RAIZ, "datos")


DATOS = _datos()

# ★ La cuenta de cada jugador: `<ESTADO>/cuentas/<nombre>.json` (la vieja `cuenta.json` pasa a ser
#   la de «rui»; se puede borrar: vuelve al inicio)
CUENTA = os.path.join(ESTADO, "cuenta.json")
CUENTAS = os.path.join(ESTADO, "cuentas")

# ★ El modo relay (ver `servidor/relay.py`): con EDA_RELAY_IP, o con el archivo `modo_relay` (adentro:
#   la IP del relay; vacío = 127.0.0.1)
RELAY_IP = os.environ.get("EDA_RELAY_IP", "")
RELAY_BANDERA = os.path.join(ESTADO, "modo_relay")
RELAY_MAPA = os.path.join(ESTADO, "relay.json")
RELAY_BASE = int(os.environ.get("EDA_RELAY_BASE") or 26000)
PUNCH_PUERTO = int(os.environ.get("EDA_PUNCH_PUERTO") or 25001)   # `herramientas/udp_punch.py`
# ★ Cómo se hablan los jugadores en la partida (MEDICIONES §39–40):
#   "directo" = P2P de verdad: cada uno recibe la dirección del OTRO (la pública que vio el punch, o
#     la privada si comparten IP pública) y su MAC real como identidad; el relay sólo para quien no
#     mandó su MAC (un juego lanzado sin comillas). La latencia es la de ellos dos, no la del server.
#   "relay" = todo pasa por el relay del server (lo de antes; para NAT que no se dejan atravesar).
P2P = os.environ.get("EDA_P2P", "directo")
PUNCH_MAPA = os.path.join(ESTADO, "punch.json")   # conexión → [IP, puerto] que vio el punch (relay_udp.py)

# ★ EL LOGIN (servidor/porteria.py, MEDICIONES §45):
#   "abierto" = como siempre: las cuentas rui / kai / mio / ren por orden de llegada (jugar en casa)
#   "pase"    = sólo entra quien trae un TICKET en el 0x100F. El launcher lo consigue canjeando acá
#               (POST /eda/pase) el PASE firmado del portero de R2Beat (Chile), que sale sólo para
#               cuentas aprobadas para EDA. La cuenta pasa a ser `r2b_<uid de R2Beat>`.
LOGIN = os.environ.get("EDA_LOGIN", "abierto")
PORTERO_CLAVES = os.environ.get("EDA_PORTERO_CLAVES", "")   # el JWKS del portero: un archivo o una URL https
PORTERO_EMISOR = "r2beat-portero"
PORTERO_AUDIENCIA = "eda"
PORTERIA = os.path.join(ESTADO, "porteria.db")              # los tickets dados y los pases ya usados
TICKET_HORAS = float(os.environ.get("EDA_TICKET_HORAS") or 12)

# ★ la LISTA DE SERVIDORES (servidor/entrada.py · lista_servidores): el nombre y el MÁXIMO de jugadores
#   (con los conectados de verdad, el cliente muestra [Open] / [Normal] / [Busy] / [Full])
NOMBRE_SERVER = os.environ.get("EDA_NOMBRE_SERVER") or "EDA"
MAX_JUGADORES = int(os.environ.get("EDA_MAX_JUGADORES") or 100)

# ★ «al menos por ahora, directo nivel 25» (El tester, 12-nov): el piso de nivel de cada personaje
#   (servidor/cuentas.py · con_nivel_inicial). 0 = sin piso (las pruebas lo usan así)
NIVEL_INICIAL = int(os.environ.get("EDA_NIVEL_INICIAL") or 25)

# ★ para probar a mano: lo que se deje en este archivo ([["1069", "00"], …]) sale con el próximo
#   «estoy vivo» (0x1001), y el archivo se borra
EMPUJAR = os.path.join(ESTADO, "empujar.json")

# Los XML del juego (de `Data.dat`, con `herramientas/sacar_xml.py`). Son de Softnyx; el repositorio
#   público los trae en `datos/` (lo pidió el dueño del proyecto, 11-nov: ver AVISO-LEGAL.md)
PRODUCTOS_XML = os.path.join(DATOS, "Product.xml")
HABILIDADES_XML = os.path.join(DATOS, "Skill.xml")
PREMIOS_XML = os.path.join(DATOS, "StageReward.xml")
TIPOS_XML = os.path.join(DATOS, "ItemTypeList.xml")
