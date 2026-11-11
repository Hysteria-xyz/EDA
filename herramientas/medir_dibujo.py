r"""medir_dibujo -- ¿QUÉ trabajo le da EDA a la placa de video, pantalla por pantalla?

Lanza `_trabajo/juego/EDA_limpio.exe` con Frida (ruta entre comillas) y, desde que crea su dispositivo
Direct3D 9, cuenta por segundo cada pedido al dispositivo (Present, Clear, Draw*, SetRenderTarget,
StretchRect, GetRenderTargetData, UpdateSurface/Texture, CreateTexture…), los LockRect / GetDC de
texturas y superficies (leer o escribir la imagen desde el procesador: lento en una placa moderna),
y las llamadas de dibujo de Windows (GDI: BitBlt, StretchBlt, StretchDIBits, ExtTextOut, GetDC…).
Escribe una línea JSON cada segundo en `_trabajo/dibujo_<hora>.jsonl` y, al final, un resumen.

    py herramientas\medir_dibujo.py [segundos=120]           # el juego queda para que lo maneje el piloto
    py herramientas\medir_dibujo.py analizar <archivo.jsonl>

Sólo MIDE (nada cambia en el juego).
"""
import collections
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

# IDirect3DDevice9: índice en la vtable → nombre (los que importan para el costo)
DEVICE = {16: "Reset", 17: "Present", 18: "GetBackBuffer", 23: "CreateTexture", 26: "CreateVertexBuffer",
          28: "CreateRenderTarget", 30: "UpdateSurface", 31: "UpdateTexture", 32: "GetRenderTargetData",
          33: "GetFrontBufferData", 34: "StretchRect", 35: "ColorFill", 36: "CreateOffscreenPlainSurface",
          37: "SetRenderTarget", 41: "BeginScene", 42: "EndScene", 43: "Clear", 57: "SetRenderState",
          65: "SetTexture", 81: "DrawPrimitive", 82: "DrawIndexedPrimitive", 83: "DrawPrimitiveUP",
          84: "DrawIndexedPrimitiveUP"}

JS = r"""
const DEVICE = %(device)s;
let c = {};
function cuenta(n, k) { c[n] = (c[n] || 0) + (k || 1); }
const hechos = new Set();
function enganchar(fn, nombre, extra) {
    const k = fn.toString();
    if (hechos.has(k)) return;
    hechos.add(k);
    Interceptor.attach(fn, extra ? extra : {onEnter() { cuenta(nombre); }});
}
function engancharTextura(tex) {          // IDirect3DTexture9: 19 LockRect · 18 GetSurfaceLevel
    const vt = tex.readPointer();
    enganchar(vt.add(19 * 4).readPointer(), 'Texture::LockRect', {onEnter(a) {
        cuenta('Texture::LockRect'); if ((a[4].toInt32() & 0x10) === 0) cuenta('Texture::LockRect(no READONLY)'); }});
    enganchar(vt.add(18 * 4).readPointer(), 'Texture::GetSurfaceLevel', {
        onEnter(a) { this.out = a[2]; cuenta('Texture::GetSurfaceLevel'); },
        onLeave(r) { if (r.toInt32() === 0) engancharSuperficie(this.out.readPointer()); }});
}
function engancharSuperficie(s) {         // IDirect3DSurface9: 13 LockRect · 15 GetDC · 16 ReleaseDC
    const vt = s.readPointer();
    enganchar(vt.add(13 * 4).readPointer(), 'Surface::LockRect');
    enganchar(vt.add(15 * 4).readPointer(), 'Surface::GetDC');
}
function engancharDevice(dev) {
    const vt = dev.readPointer();
    for (const i in DEVICE) {
        const n = DEVICE[i];
        if (n === 'Clear') {
            enganchar(vt.add(i * 4).readPointer(), n, {onEnter(a) { cuenta('Clear'); cuenta('Clear(rects ' + a[1].toInt32() + ')'); }});
        } else if (n === 'CreateTexture') {
            enganchar(vt.add(i * 4).readPointer(), n, {
                // (this, ancho, alto, niveles, uso, formato, POOL, ppTextura, compartida)
                onEnter(a) { this.out = a[7]; cuenta('CreateTexture');
                             cuenta('CreateTexture ' + a[1].toInt32() + 'x' + a[2].toInt32() + ' pool ' + a[6].toInt32()); },
                onLeave(r) { if (r.toInt32() === 0) engancharTextura(this.out.readPointer()); }});
        } else if (n === 'GetBackBuffer') {
            enganchar(vt.add(i * 4).readPointer(), n, {
                onEnter(a) { this.out = a[4]; cuenta(n); },
                onLeave(r) { if (r.toInt32() === 0) engancharSuperficie(this.out.readPointer()); }});
        } else if (n === 'DrawPrimitiveUP' || n === 'DrawPrimitive' || n === 'DrawIndexedPrimitive' || n === 'DrawIndexedPrimitiveUP') {
            // dónde va la cantidad de primitivas: DIP (…, primCount) 6 · DIPUP 4 · DPUP (tipo, primCount…) 2 · DP 3
            const idx = {DrawIndexedPrimitive: 6, DrawIndexedPrimitiveUP: 4, DrawPrimitiveUP: 2, DrawPrimitive: 3}[n];
            enganchar(vt.add(i * 4).readPointer(), n, {onEnter(a) { cuenta(n); cuenta(n + ' prims', a[idx].toInt32()); }});
        } else {
            enganchar(vt.add(i * 4).readPointer(), n);
        }
    }
}
function engancharD3D(d3d) {
    Interceptor.attach(d3d.readPointer().add(16 * 4).readPointer(), {
        onEnter(a) { this.out = a[6]; },
        onLeave(r) { if (r.toInt32() === 0) engancharDevice(this.out.readPointer()); }});
}
const d3d9 = Module.load('d3d9.dll');
Interceptor.attach(d3d9.getExportByName('Direct3DCreate9'), {onLeave(r) { if (!r.isNull()) engancharD3D(r); }});
// GDI y user32
const gdi = Process.getModuleByName('gdi32.dll'), u32 = Process.getModuleByName('user32.dll');
for (const [m, nombres] of [[gdi, ['BitBlt', 'StretchBlt', 'StretchDIBits', 'SetDIBitsToDevice', 'ExtTextOutW', 'ExtTextOutA',
                                    'TextOutW', 'TextOutA', 'GetDIBits', 'CreateDIBSection', 'CreateCompatibleDC', 'CreateCompatibleBitmap']],
                            [u32, ['GetDC', 'ReleaseDC', 'BeginPaint', 'InvalidateRect', 'UpdateWindow', 'DrawTextW', 'DrawTextA', 'PeekMessageA']]]) {
    for (const n of nombres) { try { enganchar(m.getExportByName(n), n); } catch (e) {} }
}
setInterval(() => { send({t: Date.now(), c: c}); c = {}; }, 1000);
"""


def medir(segundos):
    import frida
    exe = os.path.join(JUEGO, "EDA_limpio.exe")
    pid = frida.spawn([exe], cwd=JUEGO)
    ruta = os.path.join(RAIZ, "_trabajo", "dibujo_%s.jsonl" % time.strftime("%H%M%S"))
    f = open(ruta, "w", encoding="utf-8")
    s = frida.attach(pid)
    sc = s.create_script(JS % {"device": json.dumps(DEVICE)})

    def llegó(m, d):
        if m.get("type") == "send":
            f.write(json.dumps(m["payload"]) + "\n")
            f.flush()
        elif m.get("type") == "error":
            print("⚠", m.get("description"))
    sc.on("message", llegó)
    sc.load()
    frida.resume(pid)
    print("★ EDA_limpio.exe pid %d · midiendo %d s → %s" % (pid, segundos, ruta), flush=True)
    time.sleep(segundos)
    try:
        frida.kill(pid)
    except Exception:                                         # noqa: BLE001
        pass
    f.close()
    return ruta


def analizar(ruta, desde=None, hasta=None):
    filas = [json.loads(l) for l in open(ruta, encoding="utf-8")]
    t0 = filas[0]["t"]
    print("seg  Present  Draw*  prims  Clear  SetRT  Stretch  GetRTData  LockRect  GDI-Blt  GDI-texto  PeekMsg")
    for x in filas:
        c = x["c"]
        dr = sum(v for k, v in c.items() if k.startswith("Draw") and not k.endswith("prims"))
        pr = sum(v for k, v in c.items() if k.endswith("prims"))
        lk = c.get("Texture::LockRect", 0) + c.get("Surface::LockRect", 0)
        blt = sum(c.get(k, 0) for k in ("BitBlt", "StretchBlt", "StretchDIBits", "SetDIBitsToDevice", "GetDIBits"))
        tx = sum(c.get(k, 0) for k in ("ExtTextOutW", "ExtTextOutA", "TextOutW", "TextOutA", "DrawTextW", "DrawTextA"))
        print("%3d  %7d  %5d  %5d  %5d  %5d  %7d  %9d  %8d  %7d  %9d  %7d" % (
            (x["t"] - t0) / 1000, c.get("Present", 0), dr, pr, c.get("Clear", 0), c.get("SetRenderTarget", 0),
            c.get("StretchRect", 0), c.get("GetRenderTargetData", 0), lk, blt, tx, c.get("PeekMessageA", 0)))
    total = collections.Counter()
    for x in filas:
        total.update(x["c"])
    print("\n== en total (%d s), lo que más se llamó:" % len(filas))
    for k, v in total.most_common(40):
        print("   %9d  %s" % (v, k))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["analizar"]:
        analizar(a[1])
    else:
        analizar(medir(float(a[0]) if a else 120))
