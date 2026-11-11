r"""relay_udp -- el RELAY UDP del multijugador: que se encuentren clientes en PCs distintas.

★ El problema (MEDICIONES §30): cada cliente reconoce a sus pares por la IDENTIDAD P2P que va en
  sus saludos (`0xC354` / `0xC351` / `0xC352`: la MAC en texto, 17 caracteres) y la compara con la
  que el server puso en +0xA de cada miembro de la sala. Pero el cliente NO le dice al server su
  MAC (la mandaba el launcher). Y entre PCs, además, está el NAT (cíber, LAN, simétrica).

★ La salida (todo del lado del server, el exe no se toca):
  · el server inventa una identidad por jugador («02:00:00:00:00:NN») y la pone en su miembro;
  · como dirección de cada par da un puerto de ESTE relay (RELAY_BASE + 1 + conexión);
  · el relay reenvía cada datagrama al jugador dueño de ese puerto, saliendo por el puerto del que
    lo mandó (así el que recibe ve llegar al par desde la dirección que conoce), y en el camino
    cambia la MAC real del que manda por su identidad inventada (y la inventada del que recibe
    por su MAC real, por si la nombra).
  Como todo pasa por acá, no importa el tipo de NAT de nadie.

  A quién pertenece cada dirección lo aprende de los «registrame» del punch (`0x3006`: u32 = la
  conexión, que el server le dio en el 0x1010) — por eso este relay atiende también el puerto de
  punch (RELAY_BASE). Las identidades inventadas las lee de `_trabajo/servidor/relay.json` (las
  escribe `servidor/juego.py`). Se prende en el server con el archivo `_trabajo/servidor/modo_relay`.

    py herramientas\relay_udp.py [IP de escucha=0.0.0.0]
    py herramientas\relay_udp.py control          # el cambio de identidades (con su revés)
"""
import json
import os
import re
import select
import socket
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# (con EDA_ESTADO / EDA_RELAY_BASE: los mismos que lee `servidor/config.py`; así anda en Docker)
_ESTADO = os.environ.get("EDA_ESTADO") or os.path.join(RAIZ, "_trabajo", "servidor")
MAPA = os.path.join(_ESTADO, "relay.json")
# ★ lo que vio el PUNCH: conexión → [IP, puerto] PÚBLICOS de su 0x3006. Lo lee el server para darle a
#   cada par la dirección DIRECTA del otro (P2P sin relay, `servidor/relay.dir_udp`, MEDICIONES §40)
PUNCH = os.path.join(_ESTADO, "punch.json")
LOG = (os.path.join(_ESTADO, "relay.log") if os.environ.get("EDA_ESTADO")
       else os.path.join(RAIZ, "_trabajo", "broker", "relay.log"))
RELAY_BASE = int(os.environ.get("EDA_RELAY_BASE") or 26000)
MAC = re.compile(rb"[0-9A-F]{2}(?::[0-9A-F]{2}){5}")
MAC16 = re.compile(rb"(?:[0-9A-F]\x00){2}(?::\x00(?:[0-9A-F]\x00){2}){5}")


def cambiar(datos, real_de, falsa_de, origen, destino):
    """El datagrama de `origen` para `destino`, con las identidades cambiadas: la MAC REAL del que
    manda → su identidad inventada; la inventada del que recibe → su MAC real. En texto y en
    UTF-16. Devuelve (datos, MAC vista del que manda o None)."""
    vista = None
    fo, fd = falsa_de.get(origen), falsa_de.get(destino)
    encontradas = [m.group(0) for m in MAC.finditer(datos)] + [
        m.group(0).decode("utf-16-le").encode() for m in MAC16.finditer(datos)]
    for t in encontradas:
        if fo and t.decode() not in falsa_de.values():
            vista = t
            break
    if vista and fo:
        datos = datos.replace(vista, fo.encode())
        datos = datos.replace(vista.decode().encode("utf-16-le"), fo.encode("utf-16-le"))
    rd = real_de.get(destino)
    if fd and rd:
        datos = datos.replace(fd.encode(), rd)
        datos = datos.replace(fd.encode("utf-16-le"), rd.decode().encode("utf-16-le"))
    return datos, vista


def main(ip="0.0.0.0"):
    punch = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    punch.bind((ip, RELAY_BASE))
    socks = {}                       # conexión → su socket en el relay (RELAY_BASE + 1 + n)
    dir_de = {}                      # conexión → (IP, puerto) real del cliente
    de_dir = {}                      # (IP, puerto) → conexión
    real_de = {}                     # conexión → su MAC real (aprendida de sus saludos)
    falsa_de = {}
    log = open(LOG, "a", encoding="utf-8")

    def anotar(t):
        log.write("%s %s\n" % (time.strftime("%H:%M:%S"), t))
        log.flush()

    anotar("relay escuchando %s:%d (+1+n por jugador)" % (ip, RELAY_BASE))
    ultimo_mapa = 0
    # ★ cuántos datagramas de PARTIDA pasan por acá (con P2P directo tienen que ser 0): se anota
    #   un resumen cada 30 s, si hubo alguno
    reenviados, desde = {}, time.time()
    punch_vio = {}                   # conexión → (IP, puerto) de su último 0x3006 (sólo eso: punch.json)
    try:
        json.dump({}, open(PUNCH, "w"))  # lo de una corrida anterior no vale (los números se reusan)
    except OSError:
        pass
    while True:
        if reenviados and time.time() - desde >= 30:
            anotar("reenviados en %d s: %s" % (time.time() - desde, ", ".join(
                "%d→%d: %d" % (o, d, k) for (o, d), k in sorted(reenviados.items()))))
            reenviados, desde = {}, time.time()
        try:
            if os.path.getmtime(MAPA) != ultimo_mapa:
                ultimo_mapa = os.path.getmtime(MAPA)
                mapa = {int(k): v for k, v in json.load(open(MAPA)).items()}
                falsa_de = {n: (v["falsa"] if isinstance(v, dict) else v) for n, v in mapa.items()}
                for n, v in mapa.items():
                    # de respaldo (misma PC / LAN): la dirección que declaró en su 0x100F
                    if isinstance(v, dict) and v.get("udp") and n not in dir_de:
                        ip_n, puerto_n = v["udp"]
                        d = (socket.inet_ntoa(ip_n.to_bytes(4, "big")), puerto_n)
                        dir_de[n], de_dir[d] = d, n
                        anotar("jugador %d declaró %s:%d" % (n, d[0], d[1]))
                for n in falsa_de:
                    if n not in socks:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.bind((ip, RELAY_BASE + 1 + n))
                        socks[n] = s
                anotar("mapa: %s" % sorted(falsa_de))
        except (OSError, ValueError):
            pass
        listos, _, _ = select.select([punch] + list(socks.values()), [], [], 0.5)
        for s in listos:
            datos, quien = s.recvfrom(65536)
            if s is punch:
                # 0x3006: u16 largo · u16 0x3006 · u32 conexión → de dónde viene ese jugador
                if len(datos) >= 8 and datos[2:4] == b"\x06\x30":
                    n = int.from_bytes(datos[4:8], "little")
                    if dir_de.get(n) != quien:
                        anotar("jugador %d está en %s:%d" % (n, quien[0], quien[1]))
                        # ⚠ el server REUSA los números de conexión (`servidor/red.py`): uno nuevo
                        #   en el mismo número no tiene la MAC del anterior
                        real_de.pop(n, None)
                    dir_de[n], de_dir[quien] = quien, n
                    if punch_vio.get(n) != quien:
                        punch_vio[n] = quien
                        try:
                            json.dump({str(k): list(v) for k, v in punch_vio.items()}, open(PUNCH, "w"))
                        except OSError:
                            pass
                continue
            destino = next(k for k, v in socks.items() if v is s)
            origen = de_dir.get(quien)
            if origen is None or destino not in dir_de or origen not in socks:
                anotar("descartado: de %s:%d para %d (origen %s)" % (quien[0], quien[1], destino, origen))
                continue
            nuevo, vista = cambiar(datos, real_de, falsa_de, origen, destino)
            if os.environ.get("EDA_RELAY_SIN_CAMBIO"):       # ★ el control al revés
                nuevo = datos
            if vista and origen not in real_de:
                real_de[origen] = vista
                anotar("jugador %d: su MAC real aprendida (no se anota)" % origen)
            socks[origen].sendto(nuevo, dir_de[destino])
            reenviados[(origen, destino)] = reenviados.get((origen, destino), 0) + 1


def control():
    ok = []

    def chequear(n, c):
        print("  %s %s" % ("✅" if c else "⛔", n))
        ok.append(bool(c))
    real = b"AA:BB:CC:DD:EE:01"
    falsa = {1: "02:00:00:00:00:01", 2: "02:00:00:00:00:02"}
    hola = b"\x15\x00\x54\xc3\x11\x00\x00\x00" + real
    nuevo, vista = cambiar(hola, {}, falsa, 1, 2)
    chequear("el saludo de 1 sale con SU identidad inventada", nuevo.endswith(falsa[1].encode()))
    chequear("el largo no cambia (17 caracteres por 17)", len(nuevo) == len(hola))
    chequear("y se aprende su MAC real", vista == real)
    otro = b"xx" + falsa[2].encode() + b"yy"
    nuevo, _ = cambiar(otro, {2: b"AA:BB:CC:DD:EE:02"}, falsa, 1, 2)
    chequear("la inventada del que RECIBE vuelve a ser su MAC real", nuevo == b"xxAA:BB:CC:DD:EE:02yy")
    u16 = b"\0" + real.decode().encode("utf-16-le")
    nuevo, _ = cambiar(u16, {}, falsa, 1, 2)
    chequear("también en UTF-16", falsa[1].encode("utf-16-le") in nuevo)
    nada = b"\x10\x00\x99\x99sin identidad"
    chequear("★ el revés: un datagrama sin MAC pasa IGUAL", cambiar(nada, {}, falsa, 1, 2)[0] == nada)
    nuevo, vista = cambiar(b"..." + falsa[2].encode(), {}, falsa, 1, 2)
    chequear("★ el revés: una identidad inventada no se toma por MAC real", vista is None)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "control":
        sys.exit(control())
    sys.exit(main(*a))
