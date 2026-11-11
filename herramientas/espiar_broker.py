r"""espiar_broker -- ponerse en el medio de 218.145.66.187:25000 y GUARDAR lo que manda el cliente.

★ La tarea de `documentacion/SIGUIENTE_PASO_RED.md` §3. Dos piezas en UN proceso elevado:

  1. el REDIRECTOR (WinDivert, el mismo mecanismo que `proxy_mitm.py` de R2Beat): el TCP saliente
     a `218.145.66.187:25000` se reescribe a `127.0.0.1:LOCAL`, y la vuelta se reescribe al revés,
     así el cliente cree que habla con el server de verdad. El UDP hacia/desde esa IP sólo se ANOTA
     (el de LithTech; todavía no se lo ve salir).
  2. el OYENTE en `127.0.0.1:LOCAL`: acepta, y guarda a archivo TODO lo que llega, en crudo
     (`con_NNN.bin`) y en hexa+ASCII con el tiempo de cada trozo (`espia.log`).
     ⛔ **No contesta NADA.** A propósito: si el cliente habla primero, tenemos sus bytes; si
     espera que el server hable primero, no llega nada — y eso también es un dato, que el control
     de abajo permite distinguir de «el redirector no anda».

    py herramientas\espiar_broker.py control    # ★ arranca el espía (UAC) y prueba los controles
    py herramientas\espiar_broker.py juego      # abre EDA_limpio.exe con el espía puesto
    py herramientas\espiar_broker.py parar      # lo apaga (o se apaga solo a los 60 min)
    py herramientas\espiar_broker.py contestar 0604=0607:<hex>,0609:<hex> 0708=0709:<hex>
    py herramientas\espiar_broker.py callar     # vuelve a no contestar nada
    py herramientas\espiar_broker.py estado

★ Los controles (y su revés), en `control`:
    - SIN el espía, una conexión a mano a 218.145.66.187:25000 tiene que FALLAR (el server está
      muerto). Si conectara, lo que veamos después no probaría nada del redirector.
    - CON el espía, la misma conexión tiene que CONECTAR, y unos bytes al azar mandados a mano
      tienen que aparecer, idénticos, en el `.bin` de esa conexión.
    - CON el espía, la misma IP en OTRO puerto (25001) tiene que seguir fallando y no aparecer:
      el redirector agarra sólo lo que tiene que agarrar.

⚠ El proceso elevado nace en una consola NUEVA y no le puede hablar al que lo lanzó: todo lo que
  pasa queda en `_trabajo/broker/` (y `estado.json` dice si está vivo). Por la misma razón los
  ajustes le llegan por argv y no por el entorno.
⚠ Apagarlo es seguro: cuando el proceso muere, el handle de WinDivert se cierra y el tráfico
  vuelve a la normal. No queda nada tocado en la máquina.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
SALIDA = os.path.join(RAIZ, "_trabajo", "broker")
LOG = os.path.join(SALIDA, "espia.log")
ESTADO = os.path.join(SALIDA, "estado.json")
PARAR = os.path.join(SALIDA, "parar")
REGLAS = os.path.join(SALIDA, "reglas.json")   # {comando que llega: [respuestas]}; sin él, calla
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # para paquete_broker

BROKER_IP = "218.145.66.187"        # del XML dentro de Data.dat (corrida 14)
BROKER_PUERTO = 25000
LOCAL = 25900                       # donde escucha el oyente (sólo en 127.0.0.1)
VIDA_MAX = 3 * 60 * 60              # se apaga solo a las 3 horas, por si nadie lo para
INACTIVA_MAX = 15 * 60              # corta una conexión con 15 min SIN datos (no por edad)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


def filtro():
    """El filtro de WinDivert. ⚠ Este WinDivert no acepta `not (...)` (medido en R2Beat)."""
    ida = "(ip.DstAddr == %s and tcp.DstPort == %d)" % (BROKER_IP, BROKER_PUERTO)
    vuelta = "(ip.SrcAddr == 127.0.0.1 and tcp.SrcPort == %d)" % LOCAL
    udp = "(udp and (ip.DstAddr == %s or ip.SrcAddr == %s))" % (BROKER_IP, BROKER_IP)
    return "(tcp and (%s or %s)) or %s" % (ida, vuelta, udp)


# ------------------------------------------------------------------ el proceso elevado

_log_lock = threading.Lock()


def log(m):
    linea = "%s %s" % (time.strftime("%H:%M:%S"), m)
    with _log_lock:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    print(linea, flush=True)


def hexa(d, base=0):
    out = []
    for i in range(0, len(d), 16):
        t = d[i:i + 16]
        out.append("    %06x  %-48s |%s|" % (base + i, " ".join("%02x" % c for c in t),
                                              "".join(chr(c) if 32 <= c < 127 else "." for c in t)))
    return "\n".join(out)


def atender(cli, quien, n):
    """Una conexión: guarda todo lo que llega, y contesta sólo lo que diga `reglas.json`."""
    ruta = os.path.join(SALIDA, "con_%03d.bin" % n)
    t0 = ultimo = time.time()
    total = 0
    pendiente = b""
    avisado = False
    log("[oyente] ★ conexión #%d de %s:%d  -> %s" % (n, quien[0], quien[1], os.path.basename(ruta)))
    cli.settimeout(1.0)
    with open(ruta, "wb") as f:
        while True:
            try:
                d = cli.recv(65536)
            except socket.timeout:
                if not avisado and time.time() - t0 > 5 and total == 0:
                    log("[oyente]   #%d: 5 s y NADA. ¿Espera que el server hable primero?" % n)
                    avisado = True
                # ⚠ desde el ÚLTIMO dato, no desde que se abrió: antes cortaba toda conexión a los
                #   120 s aunque el cliente mandara su 0x1001 cada 20 s, y el juego mostraba
                #   «conexión inestable» (10-nov, en el lobby)
                if time.time() - ultimo > INACTIVA_MAX:
                    log("[oyente]   #%d: %d s sin datos; la cierro yo" % (n, INACTIVA_MAX))
                    break
                continue
            except OSError as e:
                log("[oyente]   #%d: se cortó (%s)" % (n, e))
                break
            if not d:
                log("[oyente]   #%d: el cliente cerró, a los %.2f s" % (n, time.time() - t0))
                break
            ultimo = time.time()
            f.write(d)
            f.flush()
            log("[oyente]   #%d  +%.3f s  %d bytes (total %d)\n%s"
                % (n, time.time() - t0, len(d), total + len(d), hexa(d, total)))
            total += len(d)
            # ★ contestar según `reglas.json` ({"0604": ["0607:<hex>", ...], ...}): por cada
            #   mensaje ENTERO que llega se descifra, se anota el comando y, si hay regla, se
            #   contesta. Se relee en cada mensaje: se cambia sin volver a elevar.
            pendiente += d
            while len(pendiente) >= 2 and len(pendiente) >= struct.unpack_from(
                    "<H", pendiente, 0)[0] + 4:
                largo = struct.unpack_from("<H", pendiente, 0)[0] + 4
                pkt, pendiente = pendiente[:largo], pendiente[largo:]
                contestar_a(cli, n, pkt)
    cli.close()
    CONEXIONES.pop(n, None)
    try:
        sv = servidor()
        if sv is not None and hasattr(sv, "cerrada"):
            sv.cerrada(n)                                     # ★ que el server la olvide
    except Exception:                                         # noqa: BLE001
        log("[oyente]   #%d  ⛔ servidor/juego.py falló al cerrar:\n%s" % (n, traceback.format_exc()))
    log("[oyente]   #%d: %d bytes en total" % (n, total))


# ★ MULTIJUGADOR: cada conexión que ya habló queda acá con su clave y su servicio, así el server
#   le puede mandar algo a OTRA conexión (p. ej. «entró alguien a tu sala» al anfitrión).
CONEXIONES = {}


def enviar_a(n, c, cuerpo):
    import paquete_broker as P
    con = CONEXIONES.get(n)
    if con is None:
        log("[oyente]   #%d  (ya no está: no le mando %04x)" % (n, c))
        return
    p = P.armar(P.mensaje(c, cuerpo), con["clave"], con["campo2"])
    try:
        with con["lock"]:
            con["cli"].sendall(p)
        log("[oyente]   #%d  → CONTESTÉ comando %04x, cuerpo de %d" % (n, c, len(cuerpo)))
    except OSError as e:
        log("[oyente]   #%d  no pude mandar (%s)" % (n, e))


def despachar(n, resp):
    """resp: [(comando, cuerpo, ms de espera[, conexión destino])] — sin destino, a `n`."""
    for r in resp:
        c, cuerpo, espera = r[0], r[1], r[2]
        destino = r[3] if len(r) > 3 else n
        if espera:
            threading.Timer(espera / 1000.0, enviar_a, (destino, c, cuerpo)).start()
        else:
            enviar_a(destino, c, cuerpo)


def reloj():
    """★ cada segundo le pregunta al server si tiene algo que decir por TIEMPO (`tick`): así el
    game over y lo demás no esperan al «estoy vivo» del cliente."""
    while True:
        time.sleep(1.0)
        try:
            sv = servidor()
            if sv is not None and hasattr(sv, "tick"):
                resp = sv.tick(sorted(CONEXIONES))
                if resp:
                    despachar(None, resp)
        except Exception:                                     # noqa: BLE001
            log("[oyente]  ⛔ servidor/juego.py tick falló:\n%s" % traceback.format_exc())
            time.sleep(10)


def contestar_a(cli, n, pkt):
    import paquete_broker as P
    try:
        m = P.abrir(pkt)
    except P.PaqueteMalo as e:
        log("[oyente]   #%d  (no se pudo abrir: %s)" % (n, e))
        return
    cmd = "%04x" % m["comando"]
    log("[oyente]   #%d  ← comando %s, mensaje de %d (clave de %s)\n%s"
        % (n, cmd, len(m["mensaje"]), m["de"], hexa(m["mensaje"])))
    # ★ con la MISMA clave con que llegó: es la del exe de ESE cliente (md5 del exe + 00) y con
    #   el MISMO servicio en la cabecera: el cliente tira lo que no coincide (`0x744910`)
    con = CONEXIONES.get(n)
    if con is None or con["campo2"] != m["campo2"] or con["clave"] != m["clave"]:
        CONEXIONES[n] = {"cli": cli, "clave": m["clave"], "campo2": m["campo2"],
                         "lock": (con or {}).get("lock") or threading.Lock()}

    def enviar(c, cuerpo):
        enviar_a(n, c, cuerpo)

    # ★ primero el SERVER CON MEMORIA (`servidor/juego.py`), si existe: se recarga solo cuando
    #   cambia el archivo, así crece sin reiniciar el espía (= sin otro UAC). Devuelve una lista
    #   de (comando, cuerpo, milisegundos de espera) o None = «no sé, que contesten las reglas».
    resp = None
    try:
        sv = servidor()
        if sv is not None:
            resp = sv.responder(m["comando"], m["mensaje"][4:], n)
    except Exception:                                         # noqa: BLE001
        log("[oyente]   #%d  ⛔ servidor/juego.py falló:\n%s" % (n, traceback.format_exc()))
        resp = None
    if resp is not None:
        despachar(n, resp)
        return
    try:
        reglas = json.load(open(REGLAS, encoding="utf-8"))
    except (OSError, ValueError):
        return
    for r in reglas.get(cmd, []):
        c, cuerpo = r.split(":", 1)
        enviar(int(c, 16), bytes.fromhex(cuerpo))


SERVIDOR = os.path.join(RAIZ, "servidor", "juego.py")


def servidor():
    """El server de juego (`servidor/`, por módulos), recargado si cambió cualquier archivo suyo.
    None si no existe."""
    if not os.path.exists(SERVIDOR):
        return None
    if RAIZ not in sys.path:
        sys.path.insert(0, RAIZ)
    import servidor as paquete
    return paquete.cargar(avisar=lambda t: log("[oyente] " + t))


def oyente():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", LOCAL))
    s.listen(8)
    log("[oyente] escuchando 127.0.0.1:%d (%s)" % (
        LOCAL, "contesta según reglas.json" if os.path.exists(REGLAS) else "no contesta nada"))
    # ⚠ la numeración SIGUE la de las corridas anteriores: empezar de 1 pisaba las capturas viejas
    n = max([int(x[4:7]) for x in os.listdir(SALIDA)
             if x.startswith("con_") and x.endswith(".bin") and x[4:7].isdigit()] or [0])
    threading.Thread(target=reloj, daemon=True).start()
    while True:
        cli, quien = s.accept()
        n += 1
        threading.Thread(target=atender, args=(cli, quien, n), daemon=True).start()


def redirigir():
    import pydivert
    conn = {}                       # puerto del cliente -> su IP de verdad
    udp_visto = set()
    with pydivert.WinDivert(filtro()) as w:
        log("[divert] activo. filtro: %s" % filtro())
        escribir_estado(True)
        for pkt in w:
            try:
                if pkt.udp is not None:
                    clave = (pkt.src_addr, pkt.src_port, pkt.dst_addr, pkt.dst_port)
                    if clave not in udp_visto:
                        udp_visto.add(clave)
                        log("[udp] %s:%d -> %s:%d  %d bytes\n%s"
                            % (clave + (len(pkt.payload or b""),
                                        hexa((pkt.payload or b"")[:256]))))
                    w.send(pkt)
                elif pkt.dst_addr == BROKER_IP and pkt.dst_port == BROKER_PUERTO:
                    if pkt.src_port not in conn:
                        log("[divert] TCP del cliente %s:%d -> %s:%d  ⇒ a 127.0.0.1:%d"
                            % (pkt.src_addr, pkt.src_port, BROKER_IP, BROKER_PUERTO, LOCAL))
                    conn[pkt.src_port] = pkt.src_addr
                    pkt.dst_addr = "127.0.0.1"
                    pkt.dst_port = LOCAL
                    pkt.src_addr = "127.0.0.1"
                    w.send(pkt)
                elif pkt.src_addr == "127.0.0.1" and pkt.src_port == LOCAL:
                    ip_cli = conn.get(pkt.dst_port)
                    if ip_cli:
                        pkt.src_addr = BROKER_IP
                        pkt.src_port = BROKER_PUERTO
                        pkt.dst_addr = ip_cli
                    w.send(pkt)
                else:
                    w.send(pkt)
            except Exception as e:                           # noqa: BLE001
                # el paquete SIEMPRE sigue su camino; el error queda anotado
                try:
                    w.send(pkt)
                except Exception:                            # noqa: BLE001
                    pass
                log("[divert] ⚠ %s: %s" % (type(e).__name__, e))


def escribir_estado(activo):
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "activo": activo, "local": LOCAL,
                   "desde": time.strftime("%Y-%m-%d %H:%M:%S")}, f)


def vigilar():
    """Se apaga si aparece el archivo `parar` o a la hora. ⚠ `os._exit` a propósito: el bucle de
    WinDivert está bloqueado en un recv; al morir el proceso el handle se cierra solo."""
    t0 = time.time()
    while True:
        time.sleep(0.5)
        if os.path.exists(PARAR) or time.time() - t0 > VIDA_MAX:
            log("[fin] %s. WinDivert se cierra con el proceso: el tráfico vuelve a la normal."
                % ("me pidieron parar" if os.path.exists(PARAR) else "pasó la hora"))
            try:
                os.remove(PARAR)
            except OSError:
                pass
            escribir_estado(False)
            os._exit(0)


def elevado():
    os.makedirs(SALIDA, exist_ok=True)
    try:
        os.remove(PARAR)
    except OSError:
        pass
    log("")
    log("=" * 70)
    log("[corrida] pid %d  ADMIN  %s:%d -> 127.0.0.1:%d"
        % (os.getpid(), BROKER_IP, BROKER_PUERTO, LOCAL))
    escribir_estado(False)
    threading.Thread(target=vigilar, daemon=True).start()
    threading.Thread(target=oyente, daemon=True).start()
    time.sleep(0.3)
    try:
        redirigir()
    except BaseException:                                    # noqa: BLE001
        log("[fin] ⛔ EL ESPÍA SE CAYÓ:")
        for l in traceback.format_exc().rstrip().split("\n"):
            log("      " + l)
        escribir_estado(False)
        time.sleep(8)               # para que se alcance a leer en su consola
        raise


def sin_admin():
    """★ El MISMO server (oyente + reloj) SIN WinDivert, sin UAC y sin límite de tiempo: los
    clientes llegan porque `herramientas/redirigir_cliente.py` les desvía el `connect` adentro
    (Frida). Para cuando no hay nadie que acepte el UAC. Se apaga con el archivo `parar`."""
    os.makedirs(SALIDA, exist_ok=True)
    try:
        os.remove(PARAR)
    except OSError:
        pass
    log("")
    log("=" * 70)
    log("[corrida] pid %d  SIN ADMIN (sin WinDivert): oyente en 127.0.0.1:%d" % (os.getpid(), LOCAL))
    escribir_estado(True)
    threading.Thread(target=oyente, daemon=True).start()
    while not os.path.exists(PARAR):
        time.sleep(0.5)
    log("[fin] me pidieron parar (sin admin)")
    os.remove(PARAR)
    escribir_estado(False)
    return 0


# ------------------------------------------------------------------ el que lo maneja (sin admin)

def vivo(pid):
    h = k32.OpenProcess(0x1000, False, pid)       # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    c = wt.DWORD(0)
    k32.GetExitCodeProcess(h, ctypes.byref(c))
    k32.CloseHandle(h)
    return c.value == 259                          # STILL_ACTIVE


def estado():
    try:
        e = json.load(open(ESTADO, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return e if vivo(e["pid"]) else None


def arrancar(espera=90):
    if (estado() or {}).get("activo"):
        print("  (el espía ya estaba corriendo)")
        return True
    os.makedirs(SALIDA, exist_ok=True)
    try:
        os.remove(ESTADO)
    except OSError:
        pass
    print("  [uac] WinDivert exige administrador: pidiendo permisos (consola nueva)...")
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, '"%s" --elevado' % os.path.abspath(__file__), RAIZ, 1)
    if rc <= 32:
        print("  ⛔ no se elevó (código %d)%s" % (rc, " -- cancelaste el diálogo" if rc == 5 else ""))
        return False
    t0 = time.time()
    while time.time() - t0 < espera:
        if (estado() or {}).get("activo"):
            print("  ✅ espía activo (pid %d)" % estado()["pid"])
            return True
        time.sleep(0.3)
    print("  ⛔ el espía no avisó que está activo en %d s: mirar %s" % (espera, LOG))
    return False


def parar(espera=10):
    e = estado()
    if not e:
        print("  (no estaba corriendo)")
        return True
    open(PARAR, "w").close()
    t0 = time.time()
    while time.time() - t0 < espera:
        if not vivo(e["pid"]):
            print("  ✅ espía apagado")
            return True
        time.sleep(0.3)
    print("  ⛔ no se apagó")
    return False


def bins():
    return {n: os.path.getsize(os.path.join(SALIDA, n))
            for n in os.listdir(SALIDA) if n.startswith("con_") and n.endswith(".bin")} \
        if os.path.isdir(SALIDA) else {}


def intentar(puerto, datos=b"", t=4.0):
    """Conecta a mano al Broker. Devuelve (conectó, error)."""
    s = socket.socket()
    s.settimeout(t)
    try:
        s.connect((BROKER_IP, puerto))
        if datos:
            s.sendall(datos)
            time.sleep(0.8)
        return True, ""
    except OSError as e:
        return False, str(e)
    finally:
        s.close()


def control():
    import pydivert
    ok = []

    def chequear(n, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok.append(bool(c))

    # el filtro compila (sin admin)
    r = pydivert.WinDivert.check_filter(filtro())
    chequear("el filtro de WinDivert compila", r[0], "" if r[0] else str(r))

    # ★ el revés, ANTES de arrancar: sin espía, el Broker no contesta
    if estado():
        print("  ⚠ el espía ya estaba corriendo: lo apago para poder hacer el revés")
        parar()
    c, err = intentar(BROKER_PUERTO, t=4.0)
    chequear("SIN espía, %s:%d NO conecta (el server está muerto)" % (BROKER_IP, BROKER_PUERTO),
             not c, "(%s)" % err if err else "(¡conectó!)")

    if not arrancar():
        chequear("arranca el espía", False)
        return 1
    time.sleep(0.5)

    antes = bins()
    marca = b"EDA-CONTROL-" + os.urandom(12).hex().encode() + b"\x00\x01\x02\xff"
    c, err = intentar(BROKER_PUERTO, marca)
    chequear("CON espía, %s:%d conecta" % (BROKER_IP, BROKER_PUERTO), c, err)
    time.sleep(1.0)
    nuevos = {k: v for k, v in bins().items() if k not in antes}
    llego = [k for k in nuevos if open(os.path.join(SALIDA, k), "rb").read() == marca]
    chequear("los bytes mandados a mano llegan IDÉNTICOS al .bin", bool(llego),
             str(llego or nuevos))

    antes = bins()
    c, err = intentar(BROKER_PUERTO + 1, b"NO-DEBE-LLEGAR", t=4.0)
    time.sleep(0.5)
    chequear("CON espía, el puerto %d NO conecta" % (BROKER_PUERTO + 1), not c,
             "(%s)" % err if err else "(¡conectó!)")
    chequear("…y no aparece en el oyente", bins() == antes)

    print("\n%s" % ("→ TODO BIEN (el espía queda corriendo: `espiar_broker.py juego`)"
                    if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def juego(segundos=40, exe="EDA_limpio.exe"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from conexiones import tcp_de, udp_de                    # noqa: E402
    if not arrancar():
        return 1
    antes = set(bins())
    tam_log = os.path.getsize(LOG)
    ruta = os.path.join(JUEGO, exe)
    subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True)
    time.sleep(0.4)
    p = subprocess.Popen([ruta], cwd=JUEGO)
    print("★ %s  pid %d  (%d s)" % (exe, p.pid, segundos))
    t0, vistas, udps = time.time(), {}, set()
    try:
        while time.time() - t0 < segundos:
            if p.poll() is not None:
                print("  %5.1fs  ⛔ el juego salió solo, código %d" % (time.time() - t0, p.returncode))
                break
            for k, est in tcp_de(p.pid).items():
                if vistas.get(k) != est:
                    vistas[k] = est
                    print("  %5.1fs  TCP -> %s:%d  (puerto local %d)  %s"
                          % ((time.time() - t0,) + k + (est,)), flush=True)
            nu = udp_de(p.pid) - udps
            if nu:
                udps |= nu
                print("  %5.1fs  UDP escuchando en %s" % (time.time() - t0, sorted(nu)), flush=True)
            time.sleep(0.2)
    finally:
        if p.poll() is None:
            p.kill()
    time.sleep(1.0)
    print("\n— lo que anotó el espía en esta corrida —")
    with open(LOG, encoding="utf-8") as f:
        f.seek(tam_log)
        print(f.read().rstrip() or "  (nada)")
    nuevos = sorted(set(bins()) - antes)
    print("\n  conexiones nuevas: %s" % ({k: bins()[k] for k in nuevos} or "ninguna"))
    return 0


def main():
    a = sys.argv[1:]
    if a[:1] == ["--elevado"]:
        return elevado()
    cmd = a[0] if a else "estado"
    if cmd == "sin_admin":
        return sin_admin()
    if cmd == "control":
        return control()
    if cmd == "juego":
        return juego(int(a[1]) if len(a) > 1 else 40)
    if cmd == "arrancar":
        return 0 if arrancar() else 1
    if cmd == "parar":
        return 0 if parar() else 1
    if cmd == "contestar":
        # contestar 0604=0607:<hex>,0609:<hex>  0708=0709:<hex>   -> reglas.json
        reglas = {}
        for x in a[1:]:
            llega, resp = x.split("=", 1)
            reglas[llega.lower()] = [r for r in resp.split(",") if r]
            for r in reglas[llega.lower()]:
                bytes.fromhex(r.split(":", 1)[1])           # que falle ACÁ si el hexa está mal
        os.makedirs(SALIDA, exist_ok=True)
        json.dump(reglas, open(REGLAS, "w", encoding="utf-8"), indent=1)
        for k, v in reglas.items():
            print("  cuando llega %s  →  %s" % (k, ", ".join(
                "%s (%d bytes)" % (r.split(":")[0], len(r.split(":")[1]) // 2) for r in v)))
        return 0
    if cmd == "callar":
        if os.path.exists(REGLAS):
            os.remove(REGLAS)
        print("  el oyente ya no contesta")
        return 0
    e = estado()
    print("  espía: %s" % ("corriendo, pid %d, desde %s" % (e["pid"], e["desde"]) if e
                          else "apagado"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
