r"""medir_vsync -- ¿qué le pide EDA a Direct3D, y cuántas vueltas da el bucle si se le saca la sincronía?

Lanza `_trabajo/juego/EDA_limpio.exe` con Frida (ruta entre comillas), engancha `d3d9!Direct3DCreate9`
→ `IDirect3D9::CreateDevice` (y `IDirect3DDevice9::Reset`) y anota los D3DPRESENT_PARAMETERS que pide
(PresentationInterval, Windowed, SwapEffect, BackBufferCount…). Con `--forzar` les cambia el
PresentationInterval a IMMEDIATE (0x80000000 = no esperar al monitor). Cuenta las vueltas del bucle
(PeekMessage) y los Present por segundo, y cierra el juego.

    py herramientas\medir_vsync.py [segundos=12]
    py herramientas\medir_vsync.py --forzar [segundos=12]

Sólo para MEDIR (en memoria, nada se escribe en el exe).
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")

JS = r"""
const FORZAR = %(forzar)s, RAPIDO = %(rapido)s;
// RAPIDO: sin LOCKABLE_BACKBUFFER (flags 0) y SWAP_DISCARD (1) en vez de COPY (3)
function rapido(p) { if (RAPIDO) { p.add(0x2C).writeU32(0); p.add(0x18).writeU32(1); } }
let vueltas = 0, presents = 0;
const u32 = Process.getModuleByName('user32.dll');
Interceptor.attach(u32.getExportByName('PeekMessageA'), {onEnter() { vueltas++; }});
function pp(p) {
    return {ancho: p.readU32(), alto: p.add(4).readU32(), buffers: p.add(0xC).readU32(),
            swap: p.add(0x18).readU32(), ventana: p.add(0x20).readU32(), flags: p.add(0x2C).readU32(),
            hz: p.add(0x30).readU32(), intervalo: '0x' + p.add(0x34).readU32().toString(16)};
}
function engancharDevice(dev) {
    const vt = dev.readPointer();
    Interceptor.attach(vt.add(17 * 4).readPointer(), {onEnter() { presents++; }});     // Present
    Interceptor.attach(vt.add(16 * 4).readPointer(), {onEnter(a) {                     // Reset
        const antes = pp(a[1]);
        if (FORZAR) a[1].add(0x34).writeU32(0x80000000);
        rapido(a[1]);
        send({q: 'Reset', pide: antes, queda: pp(a[1])});
    }});
}
function engancharD3D(d3d) {
    const cd = d3d.readPointer().add(16 * 4).readPointer();                            // CreateDevice
    Interceptor.attach(cd, {
        onEnter(a) {
            this.pp = a[5]; this.out = a[6];
            const antes = pp(a[5]);
            if (FORZAR) a[5].add(0x34).writeU32(0x80000000);
            rapido(a[5]);
            send({q: 'CreateDevice', pide: antes, queda: pp(a[5])});
        },
        onLeave(r) { if (r.toInt32() === 0) engancharDevice(this.out.readPointer()); }
    });
}
const d3d9 = Module.load('d3d9.dll');
Interceptor.attach(d3d9.getExportByName('Direct3DCreate9'), {onLeave(r) { if (!r.isNull()) engancharD3D(r); }});
setInterval(() => { send({q: 'ritmo', vueltas: vueltas, presents: presents}); vueltas = presents = 0; }, 2000);
"""


def main():
    a = sys.argv[1:]
    forzar, rapido = "--forzar" in a, "--rapido" in a
    a = [x for x in a if x not in ("--forzar", "--rapido")]
    seg = float(a[0]) if a else 12
    import frida
    exe = os.path.join(JUEGO, "EDA_limpio.exe")
    pid = frida.spawn([exe], cwd=JUEGO)                      # (Frida pone la ruta entre comillas)
    s = frida.attach(pid)
    eventos = []
    sc = s.create_script(JS % {"forzar": "true" if forzar else "false", "rapido": "true" if rapido else "false"})
    sc.on("message", lambda m, d: eventos.append(m.get("payload", m)))
    sc.load()
    frida.resume(pid)
    time.sleep(seg)
    try:
        frida.kill(pid)
    except Exception:                                         # noqa: BLE001
        pass
    print("== %s" % ("RÁPIDO (sin búfer bloqueable, SWAP_DISCARD)" if rapido else
                    ("FORZANDO IMMEDIATE (sin sincronía)" if forzar else "tal cual")))
    for e in eventos:
        if isinstance(e, dict) and e.get("q") in ("CreateDevice", "Reset"):
            print("  %s pide %s" % (e["q"], json.dumps(e["pide"])))
            if forzar or rapido:
                print("  %s queda %s" % (e["q"], json.dumps(e["queda"])))
    ritmo = [e for e in eventos if isinstance(e, dict) and e.get("q") == "ritmo"][2:]   # (sin el arranque)
    for e in ritmo:
        print("  cada 2 s: %4d vueltas (%5.1f/s) · %4d Present (%5.1f/s)"
              % (e["vueltas"], e["vueltas"] / 2, e["presents"], e["presents"] / 2))


if __name__ == "__main__":
    main()
