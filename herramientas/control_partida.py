r"""control_partida -- manejar al personaje EN LA PARTIDA sin teclado ni mouse de nadie.

EDA lee el teclado y el mouse por **DirectInput** (`dinput8`, LithTech: `enabledevice "##keyboard"`
+ `rangebind` en `autoexec.cfg`), no por mensajes de ventana: los `PostMessage` de `clic_juego.py`
no mueven al personaje. Es el método de R2Beat (`herramientas/qa/jugar_solo.py`: Frida contesta
las funciones de entrada del juego con un teclado de mentira), pero un piso más abajo:

  · adentro del juego (Frida) se crea un `IDirectInput8` propio, se le pide un teclado y se lee
    de su vtable dónde están `GetDeviceState` (9) y `GetDeviceData` (10) de dinput8 — las MISMAS
    funciones que usan los dispositivos del juego;
  · ★ MEDIDO (10-nov): el juego lee **`GetDeviceData`** (entrada CON BUFFER, registros
    `DIDEVICEOBJECTDATA` de 20 bytes), ~50 veces por segundo, desde `0x4450CF`, dos
    dispositivos (teclado y mouse). Y ⚠ **sólo si la ventana está activa**: sin foco no llama a
    nada. Con `WM_ACTIVATEAPP(1)` + `WM_ACTIVATE(1)` por mensaje (como R2Beat en
    `qa/ventanas.py`) vuelve a leer, sin traer la ventana al frente;
  · a la SALIDA de `GetDeviceData` se le AGREGAN al buffer los registros que pedimos (tecla
    abajo = `dwData 0x80`, arriba = 0; botón del mouse = `DIMOFS_BUTTONn`; giro = `DIMOFS_X`).
    Cuál dispositivo es cuál lo dice su `GetCapabilities` (`dwDevType`: 0x12 mouse, 0x13 teclado).

    py herramientas\control_partida.py medir [s]          # qué llama el juego (y con qué tamaños)
    py herramientas\control_partida.py tecla W 2          # mantener W 2 segundos
    py herramientas\control_partida.py plan "W:2 clic:0.3 girar=300 W+clic:1 nada:0.5"
    py herramientas\control_partida.py control            # el control (con su revés)

Teclas: los nombres de `autoexec.cfg` (W A S D, ESPACIO, SHIFT, 1..7, F1..F8, ARRIBA…) o `##n`
(código DIK). `clic`/`clicd` = botón izquierdo/derecho del mouse. `girar=n` = mover el mouse n en X.
"""
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

import frida

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clic_juego as C                                       # noqa: E402

DIK = {"ESC": 0x01, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08,
       "TAB": 0x0F, "Q": 0x10, "W": 0x11, "E": 0x12, "ENTER": 0x1C, "A": 0x1E, "S": 0x1F,
       "D": 0x20, "F": 0x21, "SHIFT": 0x2A, "ESPACIO": 0x39, "F1": 0x3B, "F2": 0x3C, "F3": 0x3D,
       "F4": 0x3E, "F5": 0x3F, "F6": 0x40, "F7": 0x41, "F8": 0x42, "F9": 0x43, "F10": 0x44,
       "ARRIBA": 0xC8, "IZQUIERDA": 0xCB, "DERECHA": 0xCD, "ABAJO": 0xD0}

JS = r"""
'use strict';
const k32 = Process.getModuleByName('kernel32.dll');
const di = Process.findModuleByName('dinput8.dll') || Module.load('dinput8.dll');   // lanzado: aún no está
const exe = Process.mainModule;
const enExe = a => a.compare(exe.base) >= 0 && a.compare(exe.base.add(exe.size)) < 0;
const GetModuleHandleW = new NativeFunction(k32.getExportByName('GetModuleHandleW'), 'pointer', ['pointer']);
const DI8Create = new NativeFunction(di.getExportByName('DirectInput8Create'), 'int',
                                     ['pointer', 'uint32', 'pointer', 'pointer', 'pointer'], 'stdcall');
function guid(s) {
    const h = s.replace(/[{}-]/g, ''), b = Memory.alloc(16);
    b.writeU32(parseInt(h.substr(0, 8), 16)); b.add(4).writeU16(parseInt(h.substr(8, 4), 16));
    b.add(6).writeU16(parseInt(h.substr(12, 4), 16));
    for (let i = 0; i < 8; i++) b.add(8 + i).writeU8(parseInt(h.substr(16 + 2 * i, 2), 16));
    return b;
}
const vt = (o, i) => o.readPointer().add(4 * i).readPointer();
// ★ dónde están GetDeviceState / GetDeviceData: de un teclado PROPIO (A y W, por las dudas)
const metodos = {};
for (const iid of ['{BF798030-483A-4DA2-AA99-5D64ED369700}', '{BF798031-483A-4DA2-AA99-5D64ED369700}']) {
    const pdi = Memory.alloc(4);
    const r = DI8Create(GetModuleHandleW(ptr(0)), 0x0800, guid(iid), pdi, ptr(0));
    if (r !== 0) { send({t: 'error', m: 'DirectInput8Create ' + r}); continue; }
    const d = pdi.readPointer(), pdev = Memory.alloc(4);
    const CreateDevice = new NativeFunction(vt(d, 3), 'int', ['pointer', 'pointer', 'pointer', 'pointer'], 'stdcall');
    if (CreateDevice(d, guid('{6F1D2B61-D5A0-11CF-BFC7-444553540000}'), pdev, ptr(0)) !== 0) continue;
    const dev = pdev.readPointer();
    metodos[vt(dev, 9).toString()] = 'GetDeviceState';
    metodos[vt(dev, 10).toString()] = 'GetDeviceData';
    metodos[vt(dev, 11).toString()] = 'SetDataFormat';
}
// ★ el formato PROPIO del juego (LithTech arma uno con SÓLO los objetos atados en autoexec.cfg):
//   en la entrada con buffer, dwOfs es el offset de ESE formato, no el código DIK
let mapa = {};                                // tipo → { 'k<DIK>' | 'b<n>' | 'a<n>' : dwOfs }
function nombreObj(tipoDev, dwType, pguid) {
    const inst = (dwType >>> 8) & 0xFFFF;
    if (tipoDev === 0x13) return 'k' + inst;
    if (dwType & 0x0C) return 'b' + inst;
    return 'a' + inst;
}
// qué es cada dispositivo del juego: GetCapabilities (vtable 3), DIDEVCAPS.dwDevType & 0xFF
const tipos = {};
function tipo(dev) {
    const k = dev.toString();
    if (tipos[k] === undefined) {
        const caps = Memory.alloc(44); caps.writeU32(44);
        const f = new NativeFunction(vt(dev, 3), 'int', ['pointer', 'pointer'], 'stdcall');
        tipos[k] = f(dev, caps) === 0 ? (caps.add(8).readU32() & 0xFF) : -1;
    }
    return tipos[k];
}
let cuenta = {}, ejemplo = {}, inyectados = 0, seq = 0x7000000;
const pendientes = {0x13: [], 0x12: []};      // teclado, mouse: [ofs, data]
let teclas = {}, botones = {}, mantener = {};   // mantener: botones del mouse que se repiten
for (const [dir, nombre] of Object.entries(metodos)) {
    Interceptor.attach(ptr(dir), {
        onEnter(a) {
            if (nombre === 'SetDataFormat') {
                if (!enExe(this.returnAddress)) return;
                const t = tipo(a[0]), f = a[1], n = f.add(16).readU32(), objs = f.add(20).readPointer();
                const lista = [];
                for (let i = 0; i < n; i++) {
                    const o = objs.add(16 * i), dwType = o.add(8).readU32();
                    lista.push({ofs: o.add(4).readU32(), tipo: dwType, flags: o.add(12).readU32(),
                                nombre: nombreObj(t, dwType)});
                }
                send({t: 'formato', dev: a[0].toString(), tipoDev: t, tam: f.add(12).readU32(), objs: lista});
                return;
            }
            this.dev = a[0]; this.n = a[1].toInt32(); this.p = a[2]; this.pn = a[3];
            this.cap = (nombre === 'GetDeviceData' && !a[3].isNull()) ? a[3].readU32() : 0;
            this.flags = nombre === 'GetDeviceData' ? a[4].toInt32() : 0;
            this.ra = this.returnAddress;
        },
        onLeave(rv) {
            if (nombre === 'SetDataFormat') return;
            const t = tipo(this.dev);
            const clave = nombre + ' tipo 0x' + t.toString(16) + ' ' + this.dev + ' ' + this.n +
                          ' flags ' + this.flags + ' cap ' + this.cap + (this.p.isNull() ? ' sin buffer' : '') +
                          (enExe(this.ra) ? '' : ' (no exe)');
            cuenta[clave] = (cuenta[clave] || 0) + 1;
            if (!ejemplo[clave]) ejemplo[clave] = 'ret ' + (rv.toInt32() >>> 0).toString(16) + ' desde ' + this.ra;
            if (!enExe(this.ra) || nombre !== 'GetDeviceData' || this.p.isNull() || this.n !== 20) return;
            const cola = pendientes[t];
            if (!cola) return;
            // ★ MANTENER = repetir el «abajo» en cada lectura: medido el 10-nov, una sola tecla
            //   abajo hace saltar (ESPACIO) o pegar (clic), pero W no camina: el valor de la tecla
            //   dura un cuadro (`0x445130`: el registro pisa el valor del objeto, `+0xEC`)
            if (!cola.length) {
                const sost = t === 0x13 ? Object.keys(teclas).map(k => 'k' + k)
                                        : Object.keys(botones).filter(b => mantener[b]).map(b => 'b' + b);
                sost.forEach(o => cola.push([o, 0x80]));
                if (!cola.length) return;
            }
            let n = (rv.toInt32() >= 0) ? this.pn.readU32() : 0;
            while (cola.length && n < this.cap) {
                const [obj, data] = cola.shift();
                const ofs = (mapa[t] && mapa[t][obj] !== undefined) ? mapa[t][obj] : null;
                if (ofs === null) { send({t: 'error', m: 'sin offset para ' + obj + ' (tipo ' + t + ')'}); continue; }
                const r = this.p.add(20 * n);
                r.writeU32(ofs); r.add(4).writeU32(data >>> 0); r.add(8).writeU32(Date.now() >>> 0);
                r.add(12).writeU32(seq++); r.add(16).writeU32(0);
                n++; inyectados++;
            }
            this.pn.writeU32(n);
            rv.replace(ptr(0));
        }
    });
}
send({t: 'listo', metodos: metodos});
rpc.exports = {
    poner(ts, bs) {
        const nt = {}, nb = {};
        ts.forEach(k => nt[k] = 1); bs.forEach(b => nb[b] = 1);
        for (const k in teclas) if (!nt[k]) pendientes[0x13].push(['k' + k, 0]);
        for (const k in nt) if (!teclas[k]) pendientes[0x13].push(['k' + k, 0x80]);
        for (const b in botones) if (!nb[b]) pendientes[0x12].push(['b' + b, 0]);
        for (const b in nb) if (!botones[b]) pendientes[0x12].push(['b' + b, 0x80]);
        teclas = nt; botones = nb;
    },
    girar(dx, dy) { if (dx) pendientes[0x12].push(['a0', dx | 0]); if (dy) pendientes[0x12].push(['a1', dy | 0]); },
    mapa(m) { mapa = m; },
    medicion() { const r = {cuenta: cuenta, ejemplo: ejemplo, inyectados: inyectados}; cuenta = {}; return r; },
};
"""


def pid_juego():
    p = int(os.environ["EDA_PID"]) if os.environ.get("EDA_PID") else C.pid_de()
    if not p:
        raise SystemExit("⛔ EDA_limpio.exe no está abierto")
    return p


def activar(pid):
    """★ sin foco el juego NO lee DirectInput; así cree que lo tiene (no trae la ventana al frente)."""
    h = C.ventana(pid)
    C.u32.PostMessageW(h, 0x1C, 1, 0)       # WM_ACTIVATEAPP(1)
    C.u32.PostMessageW(h, 0x06, 1, 0)       # WM_ACTIVATE(WA_ACTIVE)
    C.u32.PostMessageW(h, 0x07, 0, 0)       # WM_SETFOCUS


FORMATO = os.path.join(C.RAIZ, "_trabajo", "entrada_formato.json")
JUEGO = os.path.join(C.RAIZ, "_trabajo", "juego")


def lanzar():
    """★ Abre EDA_limpio.exe BAJO Frida (suspendido → enganchado → sigue) para ver el
    `SetDataFormat` del juego: pasa una sola vez, al armar los dispositivos. Guarda la tabla
    objeto → offset en `_trabajo/entrada_formato.json` y suelta el juego (queda abierto)."""
    import json
    subprocess.run(["taskkill", "/F", "/IM", "EDA_limpio.exe"], capture_output=True)
    time.sleep(0.5)
    # ⚠ stdio="pipe": si no, el juego HEREDA la salida de este script y un `| tail` espera a que
    #   el juego se cierre (parecía un cuelgue: medido el 10-nov, la tabla ya estaba guardada)
    pid = frida.spawn([os.path.join(JUEGO, "EDA_limpio.exe")], cwd=JUEGO, stdio="pipe")
    ses, sc, _ = conectar(pid, resumir=True)
    fin = time.time() + 60
    while time.time() < fin and len({f["tipoDev"] for f in FORMATOS}) < 2:
        time.sleep(0.2)
    mapa = {}
    for f in FORMATOS:
        mapa.setdefault(str(f["tipoDev"]), {}).update({o["nombre"]: o["ofs"] for o in f["objs"]})
        print("  formato del dispositivo tipo 0x%x: %d bytes, %d objetos" % (
            f["tipoDev"], f["tam"], len(f["objs"])))
        for o in f["objs"]:
            print("     ofs %3d  %-6s dwType %08x" % (o["ofs"], o["nombre"], o["tipo"]))
    json.dump({"mapa": mapa, "crudo": FORMATOS}, open(FORMATO, "w"), indent=1)
    print("★ pid %d  → %s" % (pid, FORMATO), flush=True)
    ses.detach()
    return pid


FORMATOS = []


def conectar(pid, resumir=False):
    ses = frida.attach(pid)
    sc = ses.create_script(JS)
    listo = []

    def al_mensaje(m, _):
        if m["type"] == "send":
            if m["payload"].get("t") == "formato":
                FORMATOS.append(m["payload"])
            elif m["payload"].get("t") == "listo":
                listo.append(m["payload"])
            else:
                print("  [js]", m["payload"])
        else:
            print("  [js error]", m.get("description"), m.get("stack", "")[:300])
    sc.on("message", al_mensaje)
    sc.load()
    for _ in range(50):
        if listo:
            break
        time.sleep(0.1)
    if not listo:
        raise SystemExit("⛔ el script no arrancó")
    if resumir:
        frida.resume(pid)
    elif os.path.exists(FORMATO):
        import json
        sc.exports_sync.mapa(json.load(open(FORMATO))["mapa"])
    else:
        print("  ⚠ sin %s: correr antes `control_partida.py lanzar`" % FORMATO)
    return ses, sc, listo[0]["metodos"]


def a_dik(nombre):
    n = nombre.upper()
    if n.startswith("##"):
        return int(n[2:])
    return DIK[n]


def plan(sc, pid, texto):
    """«W:2 clic:0.3 W+clic:1 girar=300 nada:0.5» — teclas/botones unidos con +, y segundos."""
    for paso in texto.split():
        activar(pid)
        if paso.lower().startswith("girar="):
            sc.exports_sync.girar(int(paso.split("=")[1]), 0)
            print("  %-16s" % paso)
            time.sleep(0.1)
            continue
        quien, seg = paso.rsplit(":", 1)
        ts, bs = [], []
        for q in quien.split("+"):
            # ★ en el mouse de DirectInput los ejes son las instancias 0..2 y los botones 3, 4, 5
            #   (medido en el formato del juego: «##Button 0» = instancia 3 = offset 4)
            if q.lower() == "clic":
                bs.append(3)
            elif q.lower() == "clicd":
                bs.append(4)
            elif q.lower() == "clicm":                    # el botón del medio («##Button 2»)
                bs.append(5)
            elif q.lower() != "nada":
                ts.append(a_dik(q))
        sc.exports_sync.poner(ts, bs)
        print("  %-16s %s s" % (quien, seg))
        fin = time.time() + float(seg)
        while time.time() < fin:
            time.sleep(min(0.5, max(0, fin - time.time())))
            activar(pid)
        sc.exports_sync.poner([], [])
        time.sleep(0.1)


def main():
    a = sys.argv[1:] or ["medir"]
    if a[0] == "lanzar":
        lanzar()
        return 0
    pid = pid_juego()
    ses, sc, metodos = conectar(pid)
    print("★ enganchado: %s" % ", ".join("%s %s" % (v, k) for k, v in metodos.items()))
    try:
        if a[0] == "medir":
            activar(pid)
            time.sleep(float(a[1]) if len(a) > 1 else 3)
            m = sc.exports_sync.medicion()
            for k, v in sorted(m["cuenta"].items()):
                print("  %6d × %s   (%s)" % (v, k, m["ejemplo"][k]))
            if not m["cuenta"]:
                print("  ⛔ el juego no llamó a ninguna de las dos")
        elif a[0] == "tecla":
            plan(sc, pid, "%s:%s" % (a[1], a[2] if len(a) > 2 else "1"))
        elif a[0] == "plan":
            plan(sc, pid, a[1])
        m = sc.exports_sync.medicion()
        print("  registros inyectados: %d" % m["inyectados"])
        if os.environ.get("EDA_DETALLE"):
            for k, v in sorted(m["cuenta"].items()):
                print("  %6d × %s   (%s)" % (v, k, m["ejemplo"][k]))
    finally:
        sc.exports_sync.poner([], [])
        time.sleep(0.2)
        ses.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
