r"""conexiones -- a QUÉ IP y PUERTO quiere conectarse el juego, y qué nombres resuelve.

★ El primer paso del plan de `herramientas/LEEME.md` sin pagar el precio de WinDivert: no hace
falta driver ni UAC ni elevarse. Windows mantiene la tabla de conexiones TCP/UDP **con el PID
dueño de cada una** (`GetExtendedTcpTable`), así que preguntándola cada 200 ms se ve cada intento
del juego — incluso los que fallan, porque una conexión que no contesta queda un rato en
`SYN_SENT` con la IP de destino a la vista.

    py herramientas\conexiones.py                              # abre el juego y lo mira
    py herramientas\conexiones.py --exe EDA_limpio.exe --segundos 90
    py herramientas\conexiones.py --mirar                       # mira uno que ya está abierto
    py herramientas\conexiones.py control                       # ★ el control y su revés

Deja `_trabajo/descubrir/conexiones.txt`.

⚠ Lo que esto NO ve: si el juego pregunta por un NOMBRE que ya no existe, la resolución falla y
  nunca se abre un TCP. Para esa pregunta está `mirar_dns.py` (WinDivert, se eleva). Acá se
  compensa leyendo la caché del resolvedor antes y después, que anota los nombres que SÍ
  resolvieron, y avisando explícitamente cuando no hubo ni un intento de conexión.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import socket
import struct
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
SALIDA_DIR = os.path.join(RAIZ, "_trabajo", "descubrir")
SALIDA = os.path.join(SALIDA_DIR, "conexiones.txt")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ip = ctypes.WinDLL("iphlpapi", use_last_error=True)
AF_INET = 2
TCP_TABLA_PID = 5                       # TCP_TABLE_OWNER_PID_ALL
UDP_TABLA_PID = 1                       # UDP_TABLE_OWNER_PID
ESTADOS = {1: "CERRADA", 2: "ESCUCHA", 3: "SYN_SENT", 4: "SYN_RCVD", 5: "ESTABLECIDA",
           6: "FIN_WAIT1", 7: "FIN_WAIT2", 8: "CLOSE_WAIT", 9: "CLOSING",
           10: "LAST_ACK", 11: "TIME_WAIT", 12: "DELETE_TCB"}


def _tabla(cual, tcp):
    """Los bytes crudos de la tabla, que es {cantidad, filas[]}."""
    n = wt.DWORD(0)
    f = ip.GetExtendedTcpTable if tcp else ip.GetExtendedUdpTable
    f(None, ctypes.byref(n), False, AF_INET, cual, 0)
    if not n.value:
        return b""
    b = ctypes.create_string_buffer(n.value)
    if f(b, ctypes.byref(n), False, AF_INET, cual, 0) != 0:
        return b""
    return b.raw[:n.value]


def tcp_de(pid):
    """{(ip remota, puerto remoto, puerto local): estado} de las conexiones TCP de ese proceso."""
    d = _tabla(TCP_TABLA_PID, True)
    if not d:
        return {}
    out = {}
    cuantas = struct.unpack_from("<I", d, 0)[0]
    for i in range(cuantas):
        o = 4 + i * 24          # MIB_TCPROW_OWNER_PID: estado, local, lport, remoto, rport, pid
        est, loc, lp, rem, rp, dueno = struct.unpack_from("<IIIIII", d, o)
        if dueno != pid:
            continue
        out[(socket.inet_ntoa(struct.pack("<I", rem)), socket.ntohs(rp & 0xFFFF),
             socket.ntohs(lp & 0xFFFF))] = ESTADOS.get(est, str(est))
    return out


def udp_de(pid):
    """{puerto local} de los sockets UDP de ese proceso (LithTech juega por UDP)."""
    d = _tabla(UDP_TABLA_PID, False)
    if not d:
        return set()
    out = set()
    cuantas = struct.unpack_from("<I", d, 0)[0]
    for i in range(cuantas):
        o = 4 + i * 12          # MIB_UDPROW_OWNER_PID: local, lport, pid
        loc, lp, dueno = struct.unpack_from("<III", d, o)
        if dueno == pid:
            out.add(socket.ntohs(lp & 0xFFFF))
    return out


def cache_dns():
    """{nombre} de la caché del resolvedor. Sin admin."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-DnsClientCache | Select-Object -ExpandProperty Entry"],
                           capture_output=True, timeout=40)
        return set(x.strip() for x in r.stdout.decode("latin1", "replace").splitlines()
                   if x.strip())
    except Exception:                                        # noqa: BLE001
        return set()


def pid_de(nombre):
    """El PID de un proceso ya abierto, por nombre de exe."""
    import ctypes as c

    class E(c.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("pid", wt.DWORD),
                    ("heap", c.POINTER(c.c_ulong)), ("mod", wt.DWORD), ("hilos", wt.DWORD),
                    ("padre", wt.DWORD), ("pri", c.c_long), ("flags", wt.DWORD),
                    ("exe", c.c_char * 260)]
    h = k32.CreateToolhelp32Snapshot(2, 0)
    e = E()
    e.dwSize = c.sizeof(e)
    out = None
    if k32.Process32First(h, c.byref(e)):
        while True:
            if e.exe.decode("latin1", "replace").lower() == nombre.lower():
                out = e.pid
                break
            if not k32.Process32Next(h, c.byref(e)):
                break
    k32.CloseHandle(h)
    return out


def control():
    """★ El control y su revés: una conexión que SABEMOS que existe tiene que aparecer con su
    IP y puerto, y un PID que no existe tiene que dar vacío. Sin esto, «el juego no conectó a
    nada» no significa nada: podría ser que la herramienta no vea nunca nada."""
    ok = []

    def chequear(n, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok.append(bool(c))

    s = socket.socket()
    s.settimeout(5)
    s.connect(("1.1.1.1", 80))          # un destino que contesta, para tener una conexión viva
    mio = os.getpid()
    t = tcp_de(mio)
    chequear("ve la conexión de este mismo proceso",
             any(k[0] == "1.1.1.1" and k[1] == 80 for k in t),
             str([("%s:%d" % k[:2], v) for k, v in t.items()][:3]))
    s.close()
    chequear("NO inventa conexiones de un PID que no existe", not tcp_de(0x7FFFFFF0))
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(("0.0.0.0", 0))
    chequear("ve también un socket UDP propio", u.getsockname()[1] in udp_de(mio),
             "puerto %d" % u.getsockname()[1])
    u.close()
    # ⚠ Esto NO es una prueba de que la herramienta ande: es una prueba de si ESTA MÁQUINA
    #   guarda caché de DNS. Medido el 10-nov: `Get-DnsClientCache` devuelve **0 entradas**
    #   siempre, o sea que el servicio Dnscache no está cacheando acá. ⇒ los nombres que el
    #   juego pregunte NO se pueden sacar de la caché, y para esa pregunta hay que ir a
    #   `mirar_dns.py` (WinDivert). Por eso no hace fallar al control: se avisa y se sigue.
    c = cache_dns()
    print("  %s la caché del DNS tiene %d nombres%s"
          % ("ℹ" if not c else "✅", len(c),
             "  ⇒ en esta máquina no sirve: usar mirar_dns.py (WinDivert)" if not c else ""))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="EDA_limpio.exe")
    ap.add_argument("--segundos", type=int, default=70)
    ap.add_argument("--mirar", action="store_true", help="no lo abre: mira uno ya abierto")
    a = ap.parse_args(None if sys.argv[1:2] != ["control"] else [])
    if sys.argv[1:2] == ["control"]:
        return control()

    os.makedirs(SALIDA_DIR, exist_ok=True)
    reg = open(SALIDA, "a", encoding="utf-8")
    reg.write("\n===== %s  %s =====\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), a.exe))

    dns_antes = cache_dns()
    p = None
    if a.mirar:
        pid = pid_de(os.path.basename(a.exe))
        if not pid:
            raise SystemExit("⛔ no está abierto %s" % a.exe)
    else:
        exe = a.exe if os.path.isabs(a.exe) else os.path.join(JUEGO, a.exe)
        if not os.path.exists(exe):
            raise SystemExit("⛔ no está %s" % exe)
        subprocess.run(["taskkill", "/F", "/IM", os.path.basename(exe)], capture_output=True)
        time.sleep(0.5)
        p = subprocess.Popen([exe], cwd=JUEGO)
        pid = p.pid
    print("★ %s  pid %d  (%d s)" % (a.exe, pid, a.segundos))

    t0 = time.time()
    vistas, udps = {}, set()
    try:
        while time.time() - t0 < a.segundos:
            if p is not None and p.poll() is not None:
                l = "  %5.1fs  ⛔ el juego salió solo, código %d" % (time.time() - t0, p.returncode)
                print(l)
                reg.write(l + "\n")
                break
            for k, est in tcp_de(pid).items():
                if vistas.get(k) == est:
                    continue
                vistas[k] = est
                l = "  %5.1fs  TCP -> %s:%d  (puerto local %d)  %s" % (
                    time.time() - t0, k[0], k[1], k[2], est)
                print(l, flush=True)
                reg.write(l + "\n")
            nuevos = udp_de(pid) - udps
            if nuevos:
                udps |= nuevos
                l = "  %5.1fs  UDP escuchando en %s" % (
                    time.time() - t0, ", ".join(str(x) for x in sorted(nuevos)))
                print(l, flush=True)
                reg.write(l + "\n")
            time.sleep(0.2)
    finally:
        if p is not None and p.poll() is None:
            p.kill()
        nuevos_dns = sorted(cache_dns() - dns_antes)
        if nuevos_dns:
            print("\n★ nombres que se resolvieron durante la corrida:")
            for n in nuevos_dns:
                print("    %s" % n)
                reg.write("  DNS nuevo: %s\n" % n)
        if not vistas:
            # ⚠ y esto es un dato, no un silencio: ver el aviso de arriba.
            print("\n⚠ NI UN intento de conexión TCP. O el juego no llegó a la red, o pregunta "
                  "por un nombre que no resuelve (ahí hace falta `mirar_dns.py`).")
            reg.write("  (sin conexiones TCP)\n")
        reg.close()
        print("\n   -> %s" % SALIDA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
