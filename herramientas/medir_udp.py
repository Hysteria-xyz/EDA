r"""medir_udp -- ¿dónde se va la latencia del P2P? Anota CADA datagrama UDP que mandan y reciben los juegos
abiertos (sendto / recvfrom, con el reloj de alta precisión de Windows) y los temporizadores que piden
(timeSetEvent, el timeout de select). Después cruza: cuándo sale un mensaje de A, cuándo entra a B, y
cuánto tarda B en contestar.

    py herramientas\medir_udp.py [segundos=20]        # se engancha a todos los EDA_limpio.exe / EDA.exe
    py herramientas\medir_udp.py analizar <archivo>   # vuelve a analizar una medición guardada

Sólo MIDE (no cambia nada del juego). Deja todo en `_trabajo/udp_medido_<hora>.jsonl`.
"""
import collections
import json
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JS = r"""
const k32 = Process.getModuleByName('kernel32.dll');
const qpc = new NativeFunction(k32.getExportByName('QueryPerformanceCounter'), 'int', ['pointer']);
const qpf = new NativeFunction(k32.getExportByName('QueryPerformanceFrequency'), 'int', ['pointer']);
const b = Memory.alloc(8);
qpf(b); const frec = b.readU64().toNumber();
function ahora() { qpc(b); return b.readU64().toNumber() / frec * 1000.0; }   // ms
function hex(p, n) {
    const b = new Uint8Array(p.readByteArray(Math.min(n, 12)));
    return Array.from(b, x => ('0' + x.toString(16)).slice(-2)).join('');
}
function dir(sa) {
    if (sa.isNull() || sa.readU16() !== 2) return null;
    const p = (sa.add(2).readU8() << 8) | sa.add(3).readU8();
    return [4,5,6,7].map(i => sa.add(i).readU8()).join('.') + ':' + p;
}
function puerto(s) {                       // el puerto local del socket (getsockname)
    const sa = Memory.alloc(16), l = Memory.alloc(4); l.writeU32(16);
    return gsn(s, sa, l) === 0 ? ((sa.add(2).readU8() << 8) | sa.add(3).readU8()) : 0;
}
const ws2 = Process.getModuleByName('ws2_32.dll');
const gsn = new NativeFunction(ws2.getExportByName('getsockname'), 'int', ['int', 'pointer', 'pointer']);
Interceptor.attach(ws2.getExportByName('sendto'), {onEnter(a) {
    const n = a[2].toInt32();
    send({t: ahora(), q: 'S', loc: puerto(a[0].toInt32()), otro: dir(a[4]), n: n,
          cab: hex(a[1], n)});
}});
Interceptor.attach(ws2.getExportByName('recvfrom'), {
    onEnter(a) { this.buf = a[1]; this.sa = a[4]; this.s = a[0].toInt32(); },
    onLeave(r) {
        const n = r.toInt32();
        if (n > 0) send({t: ahora(), q: 'R', loc: puerto(this.s), otro: dir(this.sa), n: n,
                         cab: hex(this.buf, n)});
    }});
Interceptor.attach(ws2.getExportByName('select'), {onEnter(a) {
    const tv = a[4];
    if (!tv.isNull()) { const ms = tv.readS32() * 1000 + tv.add(4).readS32() / 1000;
        if (!globalThis.vistos) globalThis.vistos = {};
        if (!globalThis.vistos['sel' + ms]) { globalThis.vistos['sel' + ms] = 1;
            send({t: ahora(), q: 'select', ms: ms, de: this.returnAddress.toString()}); } }
}});
const wm = Process.getModuleByName('winmm.dll');
Interceptor.attach(wm.getExportByName('timeSetEvent'), {onEnter(a) {
    send({t: ahora(), q: 'timeSetEvent', ms: a[0].toInt32(), res: a[1].toInt32(),
          tipo: a[4].toInt32(), de: this.returnAddress.toString()});
}});
send({t: ahora(), q: 'listo'});
"""


def pids_del_juego():
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return [int(l.split('","')[1]) for l in out.splitlines()
            if l.startswith('"EDA_limpio.exe"') or l.startswith('"EDA.exe"')]


def medir(segundos):
    import frida
    pids = pids_del_juego()
    if not pids:
        raise SystemExit("⛔ no hay ningún juego abierto")
    ruta = os.path.join(RAIZ, "_trabajo", "udp_medido_%s.jsonl" % time.strftime("%H%M%S"))
    f = open(ruta, "w", encoding="utf-8")
    sesiones = []
    for pid in pids:
        s = frida.attach(pid)
        sc = s.create_script(JS)

        def llegó(m, datos, pid=pid):
            if m.get("type") != "send":
                return
            p = m["payload"]
            p["pid"] = pid
            f.write(json.dumps(p) + "\n")
        sc.on("message", llegó)
        sc.load()
        sesiones.append(s)
    print("· midiendo %d s en %s …" % (segundos, pids), flush=True)
    time.sleep(segundos)
    for s in sesiones:
        s.detach()
    f.close()
    print("· guardado en %s" % ruta)
    return ruta


def analizar(ruta):
    ev = [json.loads(l) for l in open(ruta, encoding="utf-8")]
    print("== temporizadores pedidos")
    for e in ev:
        if e["q"] in ("timeSetEvent", "select"):
            print("   pid %d %-12s %s ms %s" % (e["pid"], e["q"], e["ms"], e.get("de", "")))
    dg = [e for e in ev if e["q"] in ("S", "R")]
    tipos = collections.Counter((e["q"], e["cab"][4:8] if len(e["cab"]) >= 8 else e["cab"]) for e in dg)
    print("== datagramas: %d (por sentido y tipo [bytes 2-3]):" % len(dg))
    for (q, t), n in sorted(tipos.items()):
        print("   %s %s ×%d" % (q, t, n))
    # ★ cruzar: cada envío de un juego con la recepción del MISMO contenido en otro (primeros 12 B)
    enviados = collections.defaultdict(list)
    for e in dg:
        if e["q"] == "S":
            enviados[(e["cab"], e["n"])].append(e)
    red, proc = [], collections.defaultdict(list)
    for e in dg:
        if e["q"] != "R":
            continue
        cand = [s for s in enviados[(e["cab"], e["n"])] if s["pid"] != e["pid"] and s["t"] <= e["t"]]
        if cand:
            red.append(e["t"] - max(c["t"] for c in cand))
    # tiempo de respuesta dentro de un juego: de cada recepción a su próximo envío al MISMO par
    porpid = collections.defaultdict(list)
    for e in dg:
        porpid[e["pid"]].append(e)
    for pid, lista in porpid.items():
        lista.sort(key=lambda x: x["t"])
        for i, e in enumerate(lista):
            if e["q"] == "R":
                sig = next((x for x in lista[i + 1:] if x["q"] == "S" and x["otro"] == e["otro"]), None)
                if sig and sig["t"] - e["t"] < 1000:
                    proc[pid].append(sig["t"] - e["t"])

    def resumen(v):
        v = sorted(v)
        return "n=%d · mín %.2f · mediana %.2f · p90 %.2f · máx %.2f ms" % (
            len(v), v[0], v[len(v) // 2], v[int(len(v) * 0.9)], v[-1]) if v else "sin datos"
    print("== el CABLE (sale de un juego → entra al otro): %s" % resumen(red))
    for pid, v in proc.items():
        print("== pid %d tarda en CONTESTAR (recibe → su próximo envío a ese par): %s" % (pid, resumen(v)))
    # cada cuánto LEE cada juego su socket (huecos entre recvfrom seguidos)
    for pid, lista in porpid.items():
        rs = [e["t"] for e in lista if e["q"] == "R"]
        huecos = [b - a for a, b in zip(rs, rs[1:])]
        print("== pid %d entre lecturas: %s" % (pid, resumen(huecos)))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["analizar"]:
        analizar(a[1])
    else:
        analizar(medir(float(a[0]) if a else 20))
