r"""redirigir_cliente -- llevar los clientes al server SIN WinDivert (y sin UAC).

El cliente se conecta al Broker en 218.145.66.187:25000 (de un XML de Data.dat). El espía con
WinDivert (`espiar_broker.py`) desvía ese tráfico, pero necesita administrador y se apaga a las 3
horas. Esto hace lo mismo desde ADENTRO de cada cliente: queda vigilando, y a cada `EDA_limpio.exe`
/ `EDA.exe` que aparece le engancha `ws2_32!connect` (Frida) y, si va a 218.145.66.187:25000, le
cambia el destino por 127.0.0.1:25900, donde escucha el oyente de `espiar_broker.py sin_admin`.

    py herramientas\redirigir_cliente.py            # dejarlo corriendo (en 2º plano)
    py herramientas\redirigir_cliente.py control    # el cambio del sockaddr (y su revés)

⚠ Las sesiones de Frida tienen que quedar abiertas (si este proceso se cierra, los ganchos se van
  y un cliente que se reconecte iría al Broker de verdad, que no existe).
"""
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
LOG = os.path.join(RAIZ, "_trabajo", "broker", "redirigir.log")
BROKER = ("218.145.66.187", 25000)
LOCAL = ("127.0.0.1", 25900)
if os.environ.get("EDA_SERVER"):
    # ★ a un server de OTRA PC (p. ej. el VPS): EDA_SERVER=IP[:PUERTO]
    _h, _, _p = os.environ["EDA_SERVER"].partition(":")
    LOCAL = (socket.gethostbyname(_h), int(_p or 25900))
EXES = ("EDA_limpio.exe", "EDA.exe")

JS = r"""
const quien = [%s], aca = [%s];
const f = Process.getModuleByName('ws2_32.dll').getExportByName('connect');
Interceptor.attach(f, {onEnter(a) {
    const sa = a[1];
    if (sa.readU16() !== 2) return;                         // AF_INET
    const puerto = (sa.add(2).readU8() << 8) | sa.add(3).readU8();
    const ip = [4, 5, 6, 7].map(i => sa.add(i).readU8());
    if (puerto === quien[4] && ip.every((v, i) => v === quien[i])) {
        sa.add(2).writeU8(aca[4] >> 8); sa.add(3).writeU8(aca[4] & 0xff);
        for (let i = 0; i < 4; i++) sa.add(4 + i).writeU8(aca[i]);
        send({t: 'desviado', de: ip.join('.') + ':' + puerto});
    }
}});
"""


def cambiar(sa, quien=BROKER, aca=LOCAL):
    """Lo mismo que el gancho, en Python (para el control): el sockaddr_in cambiado o igual."""
    fam, puerto = struct.unpack_from("<H", sa)[0], struct.unpack_from(">H", sa, 2)[0]
    ip = ".".join(str(b) for b in sa[4:8])
    if fam == 2 and (ip, puerto) == quien:
        return sa[:2] + struct.pack(">H", aca[1]) + bytes(int(x) for x in aca[0].split(".")) + sa[8:]
    return sa


def anotar(t):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%H:%M:%S"), t))


def pids():
    r = []
    for exe in EXES:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % exe, "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        for l in out.splitlines():
            p = [x.strip('"') for x in l.split('","')]
            if len(p) > 1 and p[1].isdigit():
                r.append(int(p[1]))
    return r


def main():
    import frida
    js = JS % (",".join(BROKER[0].split(".")) + "," + str(BROKER[1]),
               ",".join(LOCAL[0].split(".")) + "," + str(LOCAL[1]))
    sesiones = {}
    anotar("vigilando %s: %s:%d → %s:%d" % (EXES, BROKER[0], BROKER[1], LOCAL[0], LOCAL[1]))
    while True:
        vivos = set(pids())
        for p in list(sesiones):
            if p not in vivos:
                sesiones.pop(p, None)
        for p in vivos - set(sesiones):
            try:
                s = frida.attach(p)
                sc = s.create_script(js)
                sc.on("message", lambda m, d, p=p: anotar("pid %d %s" % (p, m.get("payload", m))))
                sc.load()
                sesiones[p] = (s, sc)
                anotar("pid %d enganchado" % p)
            except Exception as e:                           # noqa: BLE001
                anotar("pid %d: no se pudo (%s)" % (p, e))
                sesiones[p] = (None, None)
        time.sleep(0.3)


def control():
    ok = []

    def chequear(n, c):
        print("  %s %s" % ("✅" if c else "⛔", n))
        ok.append(bool(c))
    sa = struct.pack("<H", 2) + struct.pack(">H", 25000) + bytes([218, 145, 66, 187]) + bytes(8)
    n = cambiar(sa)
    chequear("218.145.66.187:25000 → 127.0.0.1:25900",
             n[2:8] == struct.pack(">H", 25900) + bytes([127, 0, 0, 1]) and n[8:] == bytes(8))
    otro = struct.pack("<H", 2) + struct.pack(">H", 80) + bytes([1, 2, 3, 4]) + bytes(8)
    chequear("★ el revés: otra dirección no se toca", cambiar(otro) == otro)
    otro = struct.pack("<H", 2) + struct.pack(">H", 25001) + bytes([218, 145, 66, 187]) + bytes(8)
    chequear("★ el revés: el mismo IP con otro puerto no se toca", cambiar(otro) == otro)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(control() if sys.argv[1:2] == ["control"] else main())
