r"""servidor/red.py -- el server de EDA por la RED: Linux, Docker o Windows, sin UAC ni WinDivert.

Hace lo mismo que `herramientas/espiar_broker.py sin_admin` (el de `jugar.py`), pero escuchando
en todas las interfaces y sin herramientas de Windows: así corre en un VPS. Los jugadores llegan con
`py jugar.py --server IP:PUERTO`, que desvía su `connect` del Broker de 2009 a este server.

En UN proceso:
  · el BROKER y el SERVER DE JUEGO (TCP, `EDA_PUERTO`): cada mensaje lo contesta `servidor/juego.py`
    (recargado solo cuando cambia un archivo de `servidor/`) y, si él no sabe, las reglas fijas de
    `herramientas/reglas_broker.py` (el anuncio, la lista de servidores, el NAT);
  · el RELAY UDP (`herramientas/relay_udp.py`), si hay `EDA_RELAY_IP`: con jugadores en PCs
    distintas todo el UDP de la partida pasa por acá (puertos EDA_RELAY_BASE … + EDA_MAX_CONEXIONES).

    python -m servidor.red                       # el server (lee la configuración del entorno)
    python -m servidor.red prueba HOST:PUERTO    # ★ ¿contesta? (un 0x0604 de verdad, con su revés)

Variables (además de las de `servidor/config.py`):
    EDA_ESCUCHAR    la IP donde escucha            (0.0.0.0)
    EDA_PUERTO      el puerto TCP                  (25900)
    EDA_MAX_CONEXIONES  conexiones a la vez        (200; acota los puertos del relay)
    EDA_ANUNCIO     el texto del anuncio del Broker
    EDA_LOG_HEX     1 = anotar cada mensaje en hexa (para investigar)
"""
import os
import signal
import socket
import struct
import sys
import threading
import time
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

import paquete_broker as P                                    # noqa: E402
import servidor                                               # noqa: E402
from servidor import config                                   # noqa: E402

ESCUCHAR = os.environ.get("EDA_ESCUCHAR", "0.0.0.0")
PUERTO = int(os.environ.get("EDA_PUERTO") or 25900)
MAX_CONEXIONES = int(os.environ.get("EDA_MAX_CONEXIONES") or 200)
LOG_HEX = os.environ.get("EDA_LOG_HEX") == "1"
INACTIVA_MAX = 15 * 60          # corta una conexión con 15 min SIN datos (el cliente manda 0x1001 cada 20 s)

_lock_log = threading.Lock()


def log(m):
    with _lock_log:
        print("%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m), flush=True)


# ------------------------------------------------------------------ las reglas fijas del Broker

def reglas():
    """{"0604": ["0607:<hex>", …]} — el guion de `reglas_broker.py`, armado en memoria (sin archivo)."""
    import reglas_broker as R
    if os.environ.get("EDA_ANUNCIO"):
        viejo = P.cuerpo_anuncio
        P.cuerpo_anuncio = lambda titulo, texto, *a, **k: viejo(titulo, os.environ["EDA_ANUNCIO"], *a, **k)
        try:
            return R.guion()
        finally:
            P.cuerpo_anuncio = viejo
    return R.guion()


# ------------------------------------------------------------------ las conexiones

CONEXIONES = {}                 # número → {"cli", "clave", "campo2", "lock"}
_lock_numeros = threading.Lock()
_usados = set()


def numero_libre():
    """★ El número MÁS CHICO libre (no uno que crece para siempre): el relay le da a cada jugador el
    puerto RELAY_BASE + 1 + número, así los puertos quedan acotados (y caben en un firewall)."""
    with _lock_numeros:
        n = next((k for k in range(1, MAX_CONEXIONES + 1) if k not in _usados), None)
        if n is not None:
            _usados.add(n)
        return n


def soltar(n):
    with _lock_numeros:
        _usados.discard(n)


def enviar_a(n, c, cuerpo):
    con = CONEXIONES.get(n)
    if con is None:
        log("#%d ya no está: no le mando %04x" % (n, c))
        return
    p = P.armar(P.mensaje(c, cuerpo), con["clave"], con["campo2"])
    try:
        with con["lock"]:
            con["cli"].sendall(p)
        log("#%d → %04x (%d B)" % (n, c, len(cuerpo)))
    except OSError as e:
        log("#%d no pude mandar %04x (%s)" % (n, c, e))


def despachar(n, resp):
    """resp: [(comando, cuerpo, ms de espera[, conexión destino])] — sin destino, a `n`."""
    for r in resp:
        c, cuerpo, espera = r[0], r[1], r[2]
        destino = r[3] if len(r) > 3 else n
        if espera:
            threading.Timer(espera / 1000.0, enviar_a, (destino, c, cuerpo)).start()
        else:
            enviar_a(destino, c, cuerpo)


def juego():
    return servidor.cargar(avisar=log)


def contestar(cli, n, pkt, guion):
    try:
        m = P.abrir(pkt, CONEXIONES[n]["clave"]) if n in CONEXIONES else P.abrir(pkt)
    except P.PaqueteMalo as e:
        log("#%d paquete que no se abre (%s): ¿un exe con otra clave? (EDA_CLAVES)" % (n, e))
        return
    if n not in CONEXIONES:
        CONEXIONES[n] = {"cli": cli, "clave": m["clave"], "campo2": m["campo2"], "lock": threading.Lock()}
        log("#%d clave: %s" % (n, m.get("de", "?")))
    else:
        # el cliente tira lo que no venga con SU servicio en la cabecera (`0x744910`)
        CONEXIONES[n]["campo2"] = m["campo2"]
    cmd = m["comando"]
    log("#%d ← %04x (%d B)%s" % (n, cmd, len(m["mensaje"]),
                                  ("\n" + m["mensaje"].hex(" ")) if LOG_HEX else ""))
    resp = None
    try:
        resp = juego().responder(cmd, m["mensaje"][4:], n)
    except Exception:                                         # noqa: BLE001
        log("#%d ⛔ servidor/ falló con %04x:\n%s" % (n, cmd, traceback.format_exc()))
    if resp is not None:
        despachar(n, resp)
        return
    for r in guion.get("%04x" % cmd, []):
        c, cuerpo = r.split(":", 1)
        enviar_a(n, int(c, 16), bytes.fromhex(cuerpo))


def atender(cli, quien, n, guion):
    log("#%d conectó %s:%d" % (n, quien[0], quien[1]))
    cli.settimeout(5.0)
    pendiente = b""
    ultimo = time.time()
    try:
        while True:
            try:
                d = cli.recv(65536)
            except socket.timeout:
                if time.time() - ultimo > INACTIVA_MAX:
                    log("#%d %d s sin datos: la cierro" % (n, INACTIVA_MAX))
                    break
                continue
            except OSError as e:
                log("#%d se cortó (%s)" % (n, e))
                break
            if not d:
                break
            ultimo = time.time()
            pendiente += d
            while len(pendiente) >= 2 and len(pendiente) >= struct.unpack_from("<H", pendiente, 0)[0] + 4:
                largo = struct.unpack_from("<H", pendiente, 0)[0] + 4
                pkt, pendiente = pendiente[:largo], pendiente[largo:]
                contestar(cli, n, pkt, guion)
    finally:
        cli.close()
        CONEXIONES.pop(n, None)
        try:
            juego().cerrada(n)
        except Exception:                                     # noqa: BLE001
            log("#%d ⛔ servidor/ falló al cerrar:\n%s" % (n, traceback.format_exc()))
        soltar(n)
        log("#%d cerrada" % n)


def reloj():
    """Cada segundo: lo que el server tiene que decir por TIEMPO (game over, cartas vencidas…)."""
    while True:
        time.sleep(1.0)
        try:
            resp = juego().tick(sorted(CONEXIONES))
            if resp:
                despachar(None, resp)
        except Exception:                                     # noqa: BLE001
            log("⛔ tick falló:\n%s" % traceback.format_exc())
            time.sleep(10)


def relay():
    import relay_udp
    while True:
        try:
            relay_udp.main("0.0.0.0")
        except Exception:                                     # noqa: BLE001
            log("⛔ el relay se cayó (se relanza en 5 s):\n%s" % traceback.format_exc())
            time.sleep(5)


def main():
    os.makedirs(config.ESTADO, exist_ok=True)
    signal.signal(signal.SIGTERM, lambda *a: (log("SIGTERM: me apago"), os._exit(0)))
    guion = reglas()
    juego()                                                   # que un error de código salga YA
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((ESCUCHAR, PUERTO))
    s.listen(64)
    log("EDA server en %s:%d · estado %s · datos %s (%s)" % (
        ESCUCHAR, PUERTO, config.ESTADO, config.DATOS,
        "con los XML" if os.path.exists(config.PRODUCTOS_XML) else "⚠ SIN los XML: tienda y premios vacíos"))
    if config.RELAY_IP:
        log("relay UDP: IP pública %s, puertos %d … %d" % (
            config.RELAY_IP, config.RELAY_BASE, config.RELAY_BASE + MAX_CONEXIONES))
        threading.Thread(target=relay, daemon=True).start()
    else:
        log("sin relay (EDA_RELAY_IP vacío): sólo para jugadores en la MISMA PC que el server")
    threading.Thread(target=reloj, daemon=True).start()
    while True:
        cli, quien = s.accept()
        n = numero_libre()
        if n is None:
            log("⛔ lleno (%d conexiones): rechazo %s:%d" % (MAX_CONEXIONES, quien[0], quien[1]))
            cli.close()
            continue
        threading.Thread(target=atender, args=(cli, quien, n, guion), daemon=True).start()


def prueba(destino):
    """★ ¿Contesta el server? Le manda un 0x0604 (el primer mensaje del cliente) cifrado con la clave
    del EDA.exe de 2009 y espera el 0x0607 del guion. El revés: el mismo mensaje con una clave que
    nadie conoce NO tiene que tener respuesta."""
    host, _, puerto = destino.rpartition(":")
    ok = []

    def una(clave, espera_respuesta, texto):
        s = socket.create_connection((host, int(puerto)), timeout=5)
        s.sendall(P.armar(P.mensaje(0x0604, bytes(8)), clave))
        s.settimeout(3)
        try:
            d = s.recv(65536)
        except socket.timeout:
            d = b""
        s.close()
        cmds = []
        for p in P.trozos(d):
            try:
                cmds.append(P.abrir(p, clave)["comando"])
            except P.PaqueteMalo:
                cmds.append(None)
        bien = (0x0607 in cmds) if espera_respuesta else not d
        print("  %s %s → %s" % ("✅" if bien else "⛔", texto, ["%04x" % c if c else "?" for c in cmds] or "nada"))
        ok.append(bien)
    una(P.CLAVES_FIJAS["EDA.exe de 2009"], True, "0x0604 con la clave del EDA.exe de 2009")
    una(bytes(16), False, "★ el revés: con una clave que nadie conoce, no contesta")
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    if sys.argv[1:2] == ["prueba"]:
        sys.exit(prueba(sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1:%d" % PUERTO))
    sys.exit(main())
