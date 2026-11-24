r"""udp_combate -- ★ PvP, etapa 0.3: TODO el UDP de la partida entre los dos juegos, con MARCAS de lo que pasa.

`herramientas/medir_udp.py` mide latencias y guarda sólo 12 bytes de cada datagrama. Acá va el datagrama
ENTERO (hasta 1024 B) de `sendto` / `recvfrom` (ws2_32, lo mismo que engancha medir_udp), con la hora del reloj
de alta precisión de Windows (la misma para los dos juegos: se pueden ordenar juntos). Sólo MIRA.

    py herramientas\pvp\udp_combate.py capturar [segundos=120]   # los juegos de dos_clientes.py (o EDA_PIDS="1 2")
        mientras corre: escribí una palabra + Enter («quieto», «ataque», «golpe», «muere»…) = una MARCA
    py herramientas\pvp\udp_combate.py resumen <archivo.jsonl>    # qué tipos de datagrama aparecen y cuáles
                                                                  # aparecen DESPUÉS de cada marca y no antes
    py herramientas\pvp\udp_combate.py control                    # el control con un proceso de prueba (y su revés)

El archivo va a la carpeta de la sesión (udp_<hora>.jsonl). Cada línea: {t (ms), pid, juego, q: S|R|marca,
loc, otro, n, hex}.
"""
import collections
import json
import os
import subprocess
import sys
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import dos_clientes as D                                     # noqa: E402

MAX_BYTES = 1024
VENTANA_MS = 1500

JS = r"""
const k32 = Process.getModuleByName('kernel32.dll');
const qpc = new NativeFunction(k32.getExportByName('QueryPerformanceCounter'), 'int', ['pointer']);
const qpf = new NativeFunction(k32.getExportByName('QueryPerformanceFrequency'), 'int', ['pointer']);
const b8 = Memory.alloc(8);
qpf(b8); const frec = b8.readU64().toNumber();
function ahora() { qpc(b8); return b8.readU64().toNumber() / frec * 1000.0; }
function hex(p, n) {
    const b = new Uint8Array(p.readByteArray(Math.min(n, MAXB)));
    return Array.from(b, x => ('0' + x.toString(16)).slice(-2)).join('');
}
function dir(sa) {
    if (sa.isNull() || sa.readU16() !== 2) return null;
    const p = (sa.add(2).readU8() << 8) | sa.add(3).readU8();
    return [4,5,6,7].map(i => sa.add(i).readU8()).join('.') + ':' + p;
}
const ws2 = Process.getModuleByName('ws2_32.dll');
const gsn = new NativeFunction(ws2.getExportByName('getsockname'), 'int', ['pointer', 'pointer', 'pointer']);
const puertos = {};
function puerto(s) {
    const k = s.toString();
    if (puertos[k] === undefined) {
        const sa = Memory.alloc(16), l = Memory.alloc(4); l.writeU32(16);
        puertos[k] = gsn(s, sa, l) === 0 ? ((sa.add(2).readU8() << 8) | sa.add(3).readU8()) : 0;
    }
    return puertos[k];
}
Interceptor.attach(ws2.getExportByName('sendto'), {onEnter(a) {
    const n = a[2].toInt32();
    if (n > 0) send({t: ahora(), q: 'S', loc: puerto(a[0]), otro: dir(a[4]), n: n, hex: hex(a[1], n)});
}});
Interceptor.attach(ws2.getExportByName('recvfrom'), {
    onEnter(a) { this.buf = a[1]; this.sa = a[4]; this.s = a[0]; },
    onLeave(r) {
        const n = r.toInt32();
        if (n > 0) send({t: ahora(), q: 'R', loc: puerto(this.s), otro: dir(this.sa), n: n, hex: hex(this.buf, n)});
    }});
send({t: ahora(), q: 'listo'});
""".replace("MAXB", str(MAX_BYTES))


def qpc_ms():
    import ctypes
    k = ctypes.windll.kernel32
    c, f = ctypes.c_int64(), ctypes.c_int64()
    k.QueryPerformanceCounter(ctypes.byref(c))
    k.QueryPerformanceFrequency(ctypes.byref(f))
    return c.value / f.value * 1000.0


def enganchar(pids, f, candado):
    import frida
    sesiones = []
    listos = threading.Event()
    faltan = [len(pids)]
    for quien, pid in pids.items():
        s = frida.attach(pid)
        sc = s.create_script(JS)

        def llego(m, _datos, pid=pid, quien=quien):
            if m.get("type") != "send":
                if m.get("type") == "error":
                    print("  ⚠ %s: %s" % (quien, m.get("description")), flush=True)
                return
            p = m["payload"]
            if p.get("q") == "listo":
                faltan[0] -= 1
                if faltan[0] == 0:
                    listos.set()
                return
            p["pid"], p["juego"] = pid, quien
            with candado:
                f.write(json.dumps(p) + "\n")
        sc.on("message", llego)
        sc.load()
        sesiones.append(s)
    listos.wait(10)
    return sesiones


def capturar(segundos, pids=None, carpeta=None, marcas_de_stdin=True):
    if pids is None:
        if os.environ.get("EDA_PIDS"):
            pids = {"p%d" % i: int(x) for i, x in enumerate(os.environ["EDA_PIDS"].split())}
        else:
            s = D.leer_sesion()
            if not s:
                raise SystemExit("⛔ no hay sesión de dos_clientes.py (o pasá EDA_PIDS=\"pid1 pid2\")")
            pids, carpeta = s["clientes"], s["carpeta"]
    carpeta = carpeta or D.BASE
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "udp_%s.jsonl" % time.strftime("%H%M%S"))
    f = open(ruta, "w", encoding="utf-8")
    candado = threading.Lock()
    sesiones = enganchar(pids, f, candado)
    print("· capturando %d s de %s → %s" % (segundos, pids, ruta), flush=True)
    if marcas_de_stdin:
        print("  escribí una palabra + Enter para dejar una MARCA (vacío = «marca»)", flush=True)

        def leer_marcas():
            for linea in sys.stdin:
                with candado:
                    f.write(json.dumps({"t": qpc_ms(), "q": "marca", "texto": linea.strip() or "marca"}) + "\n")
                    f.flush()
                print("  · marca «%s»" % (linea.strip() or "marca"), flush=True)
        threading.Thread(target=leer_marcas, daemon=True).start()
    try:
        time.sleep(segundos)
    except KeyboardInterrupt:
        pass
    for s in sesiones:
        try:
            s.detach()
        except Exception:                                    # noqa: BLE001
            pass
    with candado:
        f.close()
    print("· guardado en %s" % ruta, flush=True)
    return ruta


def tipo(ev):
    """Clave para agrupar: el tamaño y los 2 primeros bytes. 🟡 No se sabe qué es la cabecera del UDP de LithTech:
    esto sólo separa familias para mirarlas; no afirma que esos bytes sean un «comando»."""
    return "%s %4dB %s" % (ev["q"], ev["n"], ev["hex"][:4])


def resumen(ruta, salida=print):
    evs = [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]
    datos = [e for e in evs if e.get("q") in ("S", "R")]
    marcas = sorted((e for e in evs if e.get("q") == "marca"), key=lambda e: e["t"])
    if not datos:
        salida("· sin datagramas")
        return {}
    t0, t1 = min(e["t"] for e in datos), max(e["t"] for e in datos)
    dur = max((t1 - t0) / 1000.0, 0.001)
    salida("· %d datagramas en %.1f s, %d marcas" % (len(datos), dur, len(marcas)))
    por_juego = collections.defaultdict(collections.Counter)
    for e in datos:
        por_juego[e.get("juego", e.get("pid"))][tipo(e)] += 1
    for j, c in sorted(por_juego.items(), key=lambda x: str(x[0])):
        salida("  juego %s:" % j)
        for k, n in c.most_common(12):
            salida("    %-22s %6d  (%.1f/s)" % (k, n, n / dur))
    nuevos = {}
    for m in marcas:
        antes = collections.Counter(tipo(e) for e in datos if m["t"] - VENTANA_MS <= e["t"] < m["t"])
        despues = collections.Counter(tipo(e) for e in datos if m["t"] <= e["t"] < m["t"] + VENTANA_MS)
        dif = {k: (antes.get(k, 0), n) for k, n in despues.items() if n > antes.get(k, 0)}
        nuevos[m["texto"] + "@%.0f" % m["t"]] = dif
        salida("  marca «%s» (+%.1f s): %s" % (m["texto"], (m["t"] - t0) / 1000.0,
                                             ", ".join("%s %d→%d" % (k, a, d) for k, (a, d) in
                                                       sorted(dif.items(), key=lambda x: x[1][0] - x[1][1])[:6])
                                             or "nada distinto en %d ms" % VENTANA_MS))
    return nuevos


PRUEBA = r"""
import socket, sys, time
r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); r.bind(("127.0.0.1", 0)); r.settimeout(0.05)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print(r.getsockname()[1], flush=True)
fin = time.time() + 6
while time.time() < fin:
    s.sendto(b"PVP-PRUEBA-" + bytes(range(40)), r.getsockname())
    try: r.recvfrom(2048)
    except OSError: pass
    time.sleep(0.05)
"""


def control():
    import tempfile
    ok = []

    def chequear(nombre, cond):
        ok.append(bool(cond))
        print("  %s %s" % ("✅" if cond else "⛔", nombre))

    tmp = tempfile.mkdtemp()
    hijo = subprocess.Popen([sys.executable, "-c", PRUEBA], stdout=subprocess.PIPE, text=True)
    try:
        puerto_r = int(hijo.stdout.readline())
        ruta = capturar(3, pids={"X": hijo.pid}, carpeta=tmp, marcas_de_stdin=False)
    finally:
        hijo.wait(10)
    evs = [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]
    esperado = (b"PVP-PRUEBA-" + bytes(range(40))).hex()
    s = [e for e in evs if e["q"] == "S"]
    r = [e for e in evs if e["q"] == "R"]
    chequear("captura los sendto con el datagrama ENTERO", any(e["hex"] == esperado and e["n"] == 51 for e in s))
    chequear("captura los recvfrom, con el puerto local del que recibe", any(e["hex"] == esperado and e["loc"] == puerto_r
                                                                           for e in r))
    chequear("★ el revés: nada que el proceso no mandó (todo lo capturado es la prueba)",
             evs and all(e["hex"] == esperado for e in s + r))
    sint = os.path.join(tmp, "sint.jsonl")
    with open(sint, "w", encoding="utf-8") as f:
        for i in range(40):                                   # 20 s de «quieto»: un tipo cada 500 ms
            f.write(json.dumps({"t": i * 500.0, "q": "S", "n": 20, "hex": "aa01" + "00" * 18, "juego": "A"}) + "\n")
        f.write(json.dumps({"t": 10000.0, "q": "marca", "texto": "ataque"}) + "\n")
        for i in range(3):
            f.write(json.dumps({"t": 10100.0 + i * 100, "q": "S", "n": 33, "hex": "bb07" + "00" * 31,
                                "juego": "A"}) + "\n")
        f.write(json.dumps({"t": 4000.0, "q": "marca", "texto": "quieto"}) + "\n")
    n = resumen(sint, salida=lambda *_: None)
    clave = [k for k in n if k.startswith("ataque")][0]
    chequear("resumen: después de «ataque» aparece el tipo nuevo (bb07, 33 B)",
             any("bb07" in k and v == (0, 3) for k, v in n[clave].items()))
    clave2 = [k for k in n if k.startswith("quieto")][0]
    chequear("★ el revés: con «quieto» no aparece nada nuevo", not n[clave2])
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "capturar":
        capturar(float(a[1]) if len(a) > 1 else 120)
        return 0
    if cmd == "resumen" and len(a) > 1:
        resumen(a[1])
        return 0
    if cmd == "control":
        return control()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
