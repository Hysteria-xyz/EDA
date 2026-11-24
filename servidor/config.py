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
#   ★ (21-nov) "auto" = por PAREJA y el mismo camino en los dos sentidos: misma casa → las privadas; las dos
#     públicas confiables (su 0x3006 de esta sesión y su 0x3002 por el mismo puerto) → directo; si no → relay.
#     (El anfitrión nunca manda su 0x3006: con él, relay.) Ver `servidor/relay.ruta`.
# ⚠ (21-nov) docker-compose pasa la variable SIEMPRE (vacía si el .env no la tiene): vacía = "directo", lo de
#   siempre. Un valor que no es ninguno de los tres también queda en "directo" (y se avisa al arrancar).
P2P_PEDIDO = (os.environ.get("EDA_P2P") or "").strip().lower()
P2P = P2P_PEDIDO if P2P_PEDIDO in ("directo", "relay", "auto") else "directo"
PUNCH_MAPA = os.path.join(ESTADO, "punch.json")   # conexión → [IP, puerto, hora] que vio el punch (relay_udp.py; ★ 21-nov: con hora)
# ★ P2P ENTRE CASAS (MEDICIONES §53, servidor/nat.py): cada juego se presenta al relay al conectarse
#   (0x0607 → su 0x3002) y el server le dice su dirección PÚBLICA (0x0609), como el original. Así el
#   server sabe la pública de TODOS (el anfitrión no pasa por el punch) y les da la del otro: los
#   saludos del juego abren los dos NAT. Apagado por defecto: si un NAT no deja pasar, la sala queda en
#   -1000 (peor que el relay). Se prende con EDA_P2P_ENTRE_CASAS=1 (el server de prueba, para medir)
P2P_ENTRE_CASAS = os.environ.get("EDA_P2P_ENTRE_CASAS") == "1"
NAT_MAPA = os.path.join(ESTADO, "nat.json")       # huella del 0x3002 → [IP, puerto] públicos (relay_udp.py)

# ★ EL LOGIN (servidor/porteria.py, MEDICIONES §45):
#   "abierto" = como siempre: las cuentas rui / kai / mio / ren por orden de llegada (jugar en casa)
#   "pase"    = sólo entra quien trae un TICKET en el 0x100F. El launcher lo consigue canjeando acá
#               (POST /eda/pase) el PASE firmado del portero de R2Beat (Chile), que sale sólo para
#               cuentas aprobadas para EDA. La cuenta pasa a ser `r2b_<uid de R2Beat>`.
LOGIN = os.environ.get("EDA_LOGIN", "abierto")
PORTERO_CLAVES = os.environ.get("EDA_PORTERO_CLAVES", "")   # el JWKS del portero: un archivo o una URL https
# ★ (15-nov) la clave pública del servicio de cuentas dada DIRECTO por configuración (Ed25519: 32 bytes en
#   base64url, o 64 dígitos hex). Si está, manda sobre EDA_PORTERO_CLAVES y el server no sale a buscar nada a
#   la red para arrancar ni para comprobar un pase: es como reciben la clave las demás piezas del conjunto.
CUENTAS_CLAVE_PUBLICA = (os.environ.get("EDA_CUENTAS_CLAVE_PUBLICA") or "").strip()
# ★ (15-nov) el prefijo del nombre de la cuenta: `<prefijo><número de la cuenta>`. Con el pase de Cuenta Eñeños el
#   número es el Eñeños ID (la persona), no un número de R2Beat. Hasta 4 letras, números o «_» (el nombre de un
#   personaje sin bautizar es el de su cuenta, y tiene que entrar en 12).
PREFIJO_CUENTA = os.environ.get("EDA_PREFIJO_CUENTA") or "r2b_"
# ★ (15-nov) cómo nace la cuenta de quien entra con el pase por primera vez:
#   "personaje" = como siempre: con el personaje de siempre ya hecho (y el apodo del pase lo bautiza)
#   "vacia"     = SIN personajes: el pase lo deja entrar, y sus personajes los crea él en la pantalla del
#                 juego (el cliente ya la muestra vacía: es lo que pasa cuando alguien los borra todos)
CUENTA_NUEVA = os.environ.get("EDA_CUENTA_NUEVA") or "personaje"
PORTERO_EMISOR = "r2beat-portero"
# ★ (21-nov) el `aud` del pase que acepta ESTE server: `eda` (prod) o `eda-prueba` (el server de prueba, con su pase
#   propio en Cuenta Eñeños: así una cuenta con acceso a uno no entra sola al otro, y un pase de prueba no abre prod)
PORTERO_AUDIENCIA = (os.environ.get("EDA_PORTERO_AUDIENCIA") or "eda").strip()
PORTERIA = os.path.join(ESTADO, "porteria.db")              # los tickets dados y los pases ya usados
TICKET_HORAS = float(os.environ.get("EDA_TICKET_HORAS") or 12)

# ★ la LISTA DE SERVIDORES (servidor/entrada.py · lista_servidores): el nombre y el MÁXIMO de jugadores
#   (con los conectados de verdad, el cliente muestra [Open] / [Normal] / [Busy] / [Full])
NOMBRE_SERVER = os.environ.get("EDA_NOMBRE_SERVER") or "EDA"
MAX_JUGADORES = int(os.environ.get("EDA_MAX_JUGADORES") or 100)

# ★ «al menos por ahora, directo nivel 25» (El tester, 12-nov): el piso de nivel de cada personaje
#   (servidor/cuentas.py · con_nivel_inicial). 0 = sin piso (las pruebas lo usan así)
NIVEL_INICIAL = int(os.environ.get("EDA_NIVEL_INICIAL") or 25)

# ★ (22-nov) CUENTAS DE GM (servidor/salas.py · es_gm): lista separada por comas de las cuentas que pueden
#   usar los comandos de GM en el chat (/oro, /monedas, /nivel, /item, /stats, /limpiar). Vacía por defecto = nadie es GM.
GM_CUENTAS = os.environ.get("EDA_GM_CUENTAS", "")
GM_EN_VIVO = os.environ.get("EDA_GM_EN_VIVO", "").strip() == "1"

# ★ (24-nov) EXPERIMENTAL: el server árbitro del duelo PvP (servidor/duelo.py, documentacion/PVP_PROTOTIPO.md). Apagado
#   por defecto: sin EDA_PVP=1 el server no mira los eventos PvP_* de la arena y el PvE queda exactamente igual.
PVP = os.environ.get("EDA_PVP", "").strip() == "1"
DUELOS = os.path.join(ESTADO, "duelos.jsonl")                 # cada duelo decidido: quién ganó, a quién, cómo

# ★ (20-nov) LA PUERTA INTERNA DEL PANEL del Coordinador Eñeños (servidor/panel.py, el «contrato del panel v1»):
#   R2_CUENTAS_FICHA_INTERNA es la ficha que tiene que traer cada pedido (la MISMA variable que el resto del conjunto
#   Eñeños). Vacía = la puerta no existe (todo 404). EDA_ENTORNO dice qué server es (prod, prueba, ensayo…).
FICHA_INTERNA = (os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip()
ENTORNO = os.environ.get("EDA_ENTORNO") or "local"
PANEL_AUDITORIA = os.path.join(ESTADO, "panel_auditoria.jsonl")   # cada cambio pedido por el panel, con quién

# ★ para probar a mano: lo que se deje en este archivo ([["1069", "00"], …]) sale con el próximo
#   «estoy vivo» (0x1001), y el archivo se borra
EMPUJAR = os.path.join(ESTADO, "empujar.json")

# Los XML del juego (de `Data.dat`, con `herramientas/sacar_xml.py`). Son de Softnyx; el repositorio
#   público los trae en `datos/` (lo pidió el dueño del proyecto, 11-nov: ver AVISO-LEGAL.md)
PRODUCTOS_XML = os.path.join(DATOS, "Product.xml")
HABILIDADES_XML = os.path.join(DATOS, "Skill.xml")
PREMIOS_XML = os.path.join(DATOS, "StageReward.xml")
TIPOS_XML = os.path.join(DATOS, "ItemTypeList.xml")
