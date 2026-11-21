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
    python -m servidor.red multi HOST:PUERTO     # ★ dos jugadores: sala, F9, uno se corta en la carga → el otro larga

Variables (además de las de `servidor/config.py`):
    EDA_ESCUCHAR    la IP donde escucha            (0.0.0.0)
    EDA_PUERTO      el puerto TCP                  (25900)
    EDA_MAX_CONEXIONES  conexiones a la vez        (200; acota los puertos del relay)
    EDA_ANUNCIO     el texto del anuncio del Broker
    EDA_LOG_HEX     1 = anotar cada mensaje en hexa (para investigar)
    EDA_HTTP_PUERTO / EDA_HTTP_ESCUCHAR  el login por HTTP: POST /eda/pase (PUERTO+1, 127.0.0.1;
                    afuera va con HTTPS delante). EDA_LOGIN, EDA_PORTERO_CLAVES: servidor/config.py
                    ★ El mismo HTTP atiende la puerta interna del panel del Coordinador (`/interno/panel/…`,
                    servidor/panel.py), que sólo abre con R2_CUENTAS_FICHA_INTERNA
    EDA_PANEL_ESCUCHAR  IP:PUERTO de un HTTP APARTE que sólo atiende `/interno/panel/…` (vacío = ninguno). Para
                    cuando el server corre con la red del VPS (prod / prueba) y el Coordinador vive en la red de
                    Docker: «<IP de la máquina en esa red>:25902». Ver despliegue/LEEME.md
"""
import os
import queue
import signal
import socket
import struct
import sys
import threading
import time
import traceback
import types

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
# ★ el login por HTTP (`http()`): el puerto TCP + 1 si no se dice otro; 0 = apagado
HTTP_ESCUCHAR = os.environ.get("EDA_HTTP_ESCUCHAR", "127.0.0.1")
HTTP_PUERTO = int(os.environ.get("EDA_HTTP_PUERTO") or PUERTO + 1)
PANEL_ESCUCHAR = (os.environ.get("EDA_PANEL_ESCUCHAR") or "").strip()   # «IP:PUERTO» (servidor/panel.py)
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


# ★ (20-nov, multijugador) LO QUE SALE, POR UNA COLA DE CADA CONEXIÓN. Antes `enviar_a` hacía el `sendall`
#   en el hilo de QUIEN mandaba (el de otro jugador, el reloj, un Timer): si el juego de un jugador no leía
#   (colgado, cargando, una red lenta), el hilo de su COMPAÑERO quedaba parado hasta 5 s por mensaje (el
#   timeout del socket) y sus propias respuestas se atrasaban: el lag/congelamiento pasaba de uno a otro.
#   Y si el `sendall` se cortaba por el timeout a mitad de un paquete, el resto ya no encajaba (el cliente
#   lee [largo][cuerpo]): se seguía mandando sobre un flujo roto. Ahora cada conexión tiene su escritor;
#   mandar no espera nunca, y si no se puede mandar (o la cola crece sin que el cliente lea) la conexión se
#   corta limpia, como un cierre normal (su sala, sus amigos, la lista).
COLA_MAX = int(os.environ.get("EDA_COLA_MAX") or 2000)


def escritor(n, con):
    cola = con["cola"]
    while True:
        item = cola.get()
        if item is None:
            return
        c, largo, p = item
        try:
            con["cli"].sendall(p)
            log("#%d → %04x (%d B)" % (n, c, largo))
        except OSError as e:
            log("#%d no pude mandar %04x (%s): corto la conexión (el resto no encajaría)" % (n, c, e))
            _cortar_ya(n, con)
            return


def _cortar_ya(n, con):
    con["cortada"] = True
    try:
        con["cli"].shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def enviar_a(n, c, cuerpo):
    con = CONEXIONES.get(n)
    if con is None:
        log("#%d ya no está: no le mando %04x" % (n, c))
        return
    p = P.armar(P.mensaje(c, cuerpo), con["clave"], con["campo2"])
    if "cola" not in con:                                    # (una conexión sin escritor: como antes)
        try:
            with con["lock"]:
                con["cli"].sendall(p)
            log("#%d → %04x (%d B)" % (n, c, len(cuerpo)))
        except OSError as e:
            log("#%d no pude mandar %04x (%s)" % (n, c, e))
        return
    if con.get("cortada"):
        return
    if con["cola"].qsize() >= COLA_MAX:
        log("#%d no lee: %d mensajes sin salir; corto la conexión" % (n, COLA_MAX))
        _cortar_ya(n, con)
        return
    con["cola"].put((c, len(cuerpo), p))


def cortar(n, espera=0):
    """★ Corta la conexión `n` (el «echar» del panel, servidor/panel.py): `atender` ve el corte y hace lo de
    siempre al cerrarse (su sala, sus amigos, la lista). Con `espera`, a los N segundos (que le llegue el aviso).
    ⚠ Medido en Windows (20-nov): ahí `shutdown` NO despierta al `recv` que espera (sigue dando timeout hasta que
    el otro cierra); por eso además se marca `cortada` y `atender` sale en el próximo timeout (≤ 5 s). En Linux el
    `recv` vuelve en el acto."""
    era = CONEXIONES.get(n)

    def ya():
        con = CONEXIONES.get(n)
        if con is None or con is not era:              # (ya se fue, y el número quizá es de OTRO que entró)
            return
        log("#%d la corto (panel)" % n)
        con["cortada"] = True
        try:
            con["cli"].shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    if espera:
        threading.Timer(espera, ya).start()
    else:
        ya()


def despachar(n, resp):
    """resp: [(comando, cuerpo, ms de espera[, conexión destino])] — sin destino, a `n`.
    ★ (21-nov) Pasa por `juego.ordenar_salida` (servidor/salida.py): mientras un juego carga la stage, lo que
    le cortaría la carga (0x1003–0x100B, p. ej. el chat 0x1005) se guarda y sale después de su 0x105E."""
    with servidor.CANDADO:
        try:
            resp = juego().ordenar_salida(n, resp)
        except Exception:                                     # noqa: BLE001
            log("⛔ ordenar_salida falló (se manda como antes):\n%s" % traceback.format_exc())
        for r in resp:
            c, cuerpo, espera = r[0], r[1], r[2]
            destino = r[3] if len(r) > 3 else n
            if espera:
                threading.Timer(espera / 1000.0, despachar, (destino, [(c, cuerpo, 0, destino)])).start()
            else:
                enviar_a(destino, c, cuerpo)


def juego():
    return servidor.cargar(avisar=log)


# ★ lo que la puerta del panel (servidor/panel.py) puede hacer con las conexiones: mandarles mensajes y cortarlas
PUERTA_PANEL = types.SimpleNamespace(enviar=lambda resp: despachar(None, resp), cortar=cortar)


def contestar(cli, n, pkt, guion):
    try:
        m = P.abrir(pkt, CONEXIONES[n]["clave"]) if n in CONEXIONES else P.abrir(pkt)
    except P.PaqueteMalo as e:
        log("#%d paquete que no se abre (%s): ¿un exe con otra clave? (EDA_CLAVES)" % (n, e))
        return
    if n not in CONEXIONES:
        con = {"cli": cli, "clave": m["clave"], "campo2": m["campo2"], "lock": threading.Lock(),
               "cola": queue.Queue()}
        CONEXIONES[n] = con
        threading.Thread(target=escritor, args=(n, con), daemon=True).start()
        log("#%d clave: %s" % (n, m.get("de", "?")))
    else:
        # el cliente tira lo que no venga con SU servicio en la cabecera (`0x744910`)
        CONEXIONES[n]["campo2"] = m["campo2"]
    cmd = m["comando"]
    log("#%d ← %04x (%d B)%s" % (n, cmd, len(m["mensaje"]),
                                  ("\n" + m["mensaje"].hex(" ")) if LOG_HEX else ""))
    resp = None
    # ★ (20-nov) contestar y ENCOLAR de a uno (servidor.CANDADO): así lo que el server decide en un orden sale a
    #   cada jugador en ese mismo orden, aunque dos hilos contesten a la vez. Encolar no espera (ver `escritor`).
    with servidor.CANDADO:
        try:
            resp = juego().responder(cmd, m["mensaje"][4:], n)
        except Exception:                                     # noqa: BLE001
            log("#%d ⛔ servidor/ falló con %04x:\n%s" % (n, cmd, traceback.format_exc()))
        if resp is not None:
            despachar(n, resp)
            return
    for r in guion.get("%04x" % cmd, []):
        c, cuerpo = r.split(":", 1)
        enviar_a(n, int(c, 16), bytes.fromhex(cuerpo))


def atender(cli, quien, n, guion):
    log("#%d conectó %s:%d" % (n, quien[0], quien[1]))
    # ★ la IP con que llegó (MEDICIONES §52): dos con la MISMA están en la misma casa / el mismo cíber, y
    #   se les da la dirección privada del otro (servidor/relay.py · dir_udp). (No va a ningún archivo.)
    with servidor.CANDADO:
        juego().partida(n)["ip_tcp"] = quien[0]
        juego().partida(n)["desde"] = time.time()              # (el «conectado desde» del panel)
    cli.settimeout(5.0)
    pendiente = b""
    ultimo = time.time()
    try:
        while True:
            try:
                d = cli.recv(65536)
            except socket.timeout:
                if (CONEXIONES.get(n) or {}).get("cortada"):
                    log("#%d cortada por el panel" % n)
                    break
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
        con = CONEXIONES.pop(n, None)
        if con and "cola" in con:
            con["cola"].put(None)                             # (el escritor termina)
        cli.close()
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
            with servidor.CANDADO:
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


def servidor_http(direccion, solo_panel=False):
    """★ El HTTP del server (sin arrancarlo: `serve_forever()` lo hace andar).
      · el LOGIN (servidor/porteria.py): POST /eda/pase {"pase": "<JWT del portero>"} → {"usuario", "ticket",
        "vence"}; un rechazo → {"error": código} (400 / 401 / 409 / 503). GET /eda/salud → {"login": …}.
        ⚠ Es HTTP plano: afuera se publica con HTTPS (Caddy u otro proxy delante), porque el ticket es un secreto.
      · la PUERTA INTERNA del panel del Coordinador: /interno/panel/… (servidor/panel.py: la ficha, X-R2, quién).
    `solo_panel` = sólo la puerta del panel (el HTTP aparte de EDA_PANEL_ESCUCHAR): el login ahí no existe."""
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Atender(BaseHTTPRequestHandler):
        server_version = "EDA"
        sys_version = ""

        def _json(self, codigo, datos):
            b = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def _panel(self, metodo):
            juego()                                           # (recarga servidor/ si cambió)
            from servidor import panel

            def leer_cuerpo():
                try:
                    largo = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    raise ValueError("largo")
                if not 0 <= largo <= panel.TOPE_CUERPO:
                    raise ValueError("largo")
                return self.rfile.read(largo) if largo else b""
            # ★ (20-nov) el cuerpo se lee ANTES del candado (un cliente HTTP lento no frena el juego) y el panel
            #   mira las salas y partidas de a uno con el juego (sin «el diccionario cambió mientras se recorría»)
            try:
                cuerpo, error_cuerpo = leer_cuerpo(), None
            except ValueError as e:
                cuerpo, error_cuerpo = b"", e

            def cuerpo_leido():
                if error_cuerpo is not None:
                    raise error_cuerpo
                return cuerpo
            try:
                with servidor.CANDADO:
                    codigo, datos = panel.atender(metodo, self.path, self.headers, cuerpo_leido, PUERTA_PANEL)
            except Exception:                                 # noqa: BLE001
                log("⛔ %s %s falló:\n%s" % (metodo,self.path.split("?")[0], traceback.format_exc()))
                codigo, datos = 500, {"error": "Error interno del servidor del juego."}
            self._json(codigo, datos)

        def _es_panel(self):
            ruta = self.path.split("?", 1)[0]
            return ruta == "/interno/panel" or ruta.startswith("/interno/panel/")

        def do_GET(self):
            if self._es_panel():
                return self._panel("GET")
            if self.path == "/eda/salud" and not solo_panel:
                return self._json(200, {"login": config.LOGIN})
            self._json(404, {"error": "No existe."})

        def do_POST(self):
            if self._es_panel():
                return self._panel("POST")
            if self.path == "/eda/diag" and not solo_panel:
                return self._diag()
            if self.path != "/eda/pase" or solo_panel:
                return self._json(404, {"error": "No existe."})
            try:
                largo = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                largo = -1
            if not 0 < largo <= 8192:
                return self._json(400, {"error": "largo"})
            try:
                pase = json.loads(self.rfile.read(largo)).get("pase")
            except (ValueError, AttributeError):
                return self._json(400, {"error": "formato"})
            juego()                                           # (recarga servidor/ si cambió)
            from servidor import porteria
            try:
                r = porteria.canjear(pase)
            except porteria.Rechazo as e:
                log("http %s: pase rechazado (%s)" % (self.client_address[0], e.codigo))
                return self._json(e.http, {"error": e.codigo})
            except Exception:                                 # noqa: BLE001
                log("⛔ /eda/pase falló:\n%s" % traceback.format_exc())
                return self._json(500, {"error": "interno"})
            log("http %s: ticket para la cuenta %s%s" % (self.client_address[0], config.PREFIJO_CUENTA, r["usuario"]))
            self._json(200, r)

        def _diag(self):
            """★ (21-nov) los diagnósticos de los clientes beta (servidor/diag.py). Sólo con EDA_DIAG=1: si no, 404."""
            from servidor import diag
            if not diag.ACTIVO:
                return self._json(404, {"error": "No existe."})
            try:
                largo = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                largo = -1
            if not 0 < largo <= diag.MAX_CUERPO:
                return self._json(413 if largo > diag.MAX_CUERPO else 400, {"error": "largo"})
            try:
                codigo, datos = diag.recibir(dict(self.headers.items()), self.rfile.read(largo))
            except Exception:                                 # noqa: BLE001
                log("⛔ /eda/diag falló:\n%s" % traceback.format_exc())
                codigo, datos = 500, {"error": "interno"}
            if codigo != 200:
                log("http %s: diag rechazado (%s)" % (self.client_address[0], datos.get("error")))
            self._json(codigo, datos)

        def log_message(self, *a):                            # (lo importante ya se anota arriba)
            pass

    return ThreadingHTTPServer(direccion, Atender)


def http():
    srv = servidor_http((HTTP_ESCUCHAR, HTTP_PUERTO))
    log("login por HTTP en %s:%d (modo «%s»; claves del portero: %s) · panel interno: %s" % (
        HTTP_ESCUCHAR, HTTP_PUERTO, config.LOGIN, ("por configuración (EDA_CUENTAS_CLAVE_PUBLICA)" if config.CUENTAS_CLAVE_PUBLICA else config.PORTERO_CLAVES) or "⚠ ninguna",
        "con ficha" if config.FICHA_INTERNA else "cerrado (sin R2_CUENTAS_FICHA_INTERNA)"))
    srv.serve_forever()


def http_panel():
    """★ El HTTP aparte, sólo con la puerta del panel (EDA_PANEL_ESCUCHAR = «IP:PUERTO»)."""
    ip, _, puerto = PANEL_ESCUCHAR.rpartition(":")
    while True:
        try:
            srv = servidor_http((ip, int(puerto)), solo_panel=True)
            break
        except OSError as e:                                  # (p. ej. la IP de la red de Docker todavía no está)
            log("⛔ el panel interno no pudo escuchar en %s (%s): reintento en 30 s" % (PANEL_ESCUCHAR, e))
            time.sleep(30)
    log("panel interno (sólo /interno/panel) en %s · %s" % (
        PANEL_ESCUCHAR, "con ficha" if config.FICHA_INTERNA else "cerrado (sin R2_CUENTAS_FICHA_INTERNA)"))
    srv.serve_forever()


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
        log("P2P: modo «%s»%s · entre casas: %s" % (
            config.P2P, " (⚠ EDA_P2P=%r no existe: uso «directo»)" % config.P2P_PEDIDO
            if config.P2P_PEDIDO and config.P2P_PEDIDO != config.P2P else "",
            "sí" if config.P2P_ENTRE_CASAS else "no"))
    else:
        log("sin relay (EDA_RELAY_IP vacío): sólo para jugadores en la MISMA PC que el server")
    threading.Thread(target=reloj, daemon=True).start()
    if HTTP_PUERTO:
        threading.Thread(target=http, daemon=True).start()
    if PANEL_ESCUCHAR:
        threading.Thread(target=http_panel, daemon=True).start()
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


def prueba_multi(destino):
    """★ (20-nov) MULTIJUGADOR DE PUNTA A PUNTA contra un server corriendo (como el de TEST): dos jugadores por
    TCP de verdad crean y entran a una sala, larga el anfitrión, el anfitrión termina de cargar y al otro se le
    corta el juego durante la carga. El anfitrión TIENE que largar (0x105E) en unos segundos; antes quedaba
    en la pantalla de carga para siempre. El revés: mientras el otro sigue conectado y cargando, NO larga."""
    host, _, puerto = destino.rpartition(":")
    clave = P.CLAVES_FIJAS["EDA.exe de 2009"]
    ok = []

    def chequear(texto, cond, d=""):
        print("  %s %s %s" % ("✅" if cond else "⛔", texto, d))
        ok.append(bool(cond))

    class Jugador:
        def __init__(self):
            self.s = socket.create_connection((host, int(puerto)), timeout=5)
            self.buf = b""

        def mandar(self, c, cuerpo):
            self.s.sendall(P.armar(P.mensaje(c, cuerpo), clave))

        def esperar(self, comando, segundos):
            """los mensajes hasta ver `comando` (o hasta el plazo): [(comando, cuerpo)]"""
            vistos, fin = [], time.time() + segundos
            while time.time() < fin:
                self.s.settimeout(max(0.05, fin - time.time()))
                try:
                    d = self.s.recv(65536)
                except socket.timeout:
                    break
                if not d:
                    break
                self.buf += d
                while len(self.buf) >= 2 and len(self.buf) >= struct.unpack_from("<H", self.buf)[0] + 4:
                    n = struct.unpack_from("<H", self.buf)[0] + 4
                    pkt, self.buf = self.buf[:n], self.buf[n:]
                    m = P.abrir(pkt, clave)
                    vistos.append((m["comando"], m["mensaje"][4:]))
                if any(c == comando for c, _ in vistos):
                    break
            return vistos

    a, b = Jugador(), Jugador()
    sala = bytearray(0x59)
    struct.pack_into("<I", sala, 0x28, 1011)
    sala[0x2F] = 3
    a.mandar(0x101D, bytes(4) + bytes(sala))
    r = dict(a.esperar(0x101E, 5))
    chequear("el anfitrión crea la sala (0x101E)", 0x101E in r)
    num = struct.unpack_from("<H", r.get(0x101E, bytes(16)), 5 + 4)[0]
    b.mandar(0x101F, struct.pack("<IH", 0, num) + bytes(20))
    r = dict(b.esperar(0x1020, 5))
    chequear("el otro entra (0x1020)", 0x1020 in r and r[0x1020][:2] == b"\x01\x00")
    yo_b = r.get(0x1020, b"\0\0\0\0")[3]
    b.mandar(0x1047, bytes([yo_b, 1]))
    b.esperar(0x1048, 3)
    a.mandar(0x104E, b"")
    chequear("F9: los dos reciben 0x104F", 0x104F in dict(a.esperar(0x104F, 5)) and 0x104F in dict(b.esperar(0x104F, 5)))
    a.mandar(0x105F, bytes(4))
    r = dict(a.esperar(0x105E, 2.5))
    chequear("★ el revés: con el otro todavía cargando, el anfitrión NO larga", 0x105E not in r)
    # ★ (21-nov, lo del server de prueba) el otro escribe en el chat mientras el anfitrión carga: al anfitrión NO
    #   le puede llegar el 0x1005 antes de su 0x105E (le termina el hilo de carga y no larga nunca)
    texto = "hola".encode("utf-16-le")
    b.mandar(0x100D, struct.pack("<BIII", 1, 0xFFFFFFFF, 0, len(texto)) + texto)
    antes = a.esperar(0x1005, 1.5)
    chequear("★ chat del otro durante la carga: al anfitrión no le llega todavía (se guarda)",
             0x1005 not in dict(antes), [hex(c) for c, _ in antes])
    b.s.close()                                               # (al otro se le corta el juego en la carga)
    t0 = time.time()
    vistos = a.esperar(0x105E, 8)
    r = dict(vistos)
    chequear("★ al otro se le cortó el juego → el anfitrión larga (0x105E)", 0x105E in r, "%.1f s" % (time.time() - t0))
    vistos += a.esperar(0x1005, 2)
    orden = [c for c, _ in vistos if c in (0x105E, 0x1005)]
    chequear("★ y el chat guardado le llega DESPUÉS de su 0x105E", orden[:2] == [0x105E, 0x1005], [hex(c) for c in orden])
    a.s.close()
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    if sys.argv[1:2] == ["prueba"]:
        sys.exit(prueba(sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1:%d" % PUERTO))
    if sys.argv[1:2] == ["multi"]:
        sys.exit(prueba_multi(sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1:%d" % PUERTO))
    sys.exit(main())
