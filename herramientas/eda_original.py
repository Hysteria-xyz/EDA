r"""eda_original -- abrir el EDA.exe ORIGINAL de 2009 (con ASProtect) listo para jugar contra nuestro server.

Todo pasa EN MEMORIA, el archivo no se toca:
  1. GameGuard: apenas ASProtect desempaca el código, se le ponen los 4 parches de la receta
     `limpio` de `sin_gameguard.py` (con sus bytes originales verificados antes de escribir).
  2. La red: `ws2_32!connect` a 218.145.66.187:25000 (el Broker de 2009) se desvía a
     127.0.0.1:25900, donde escucha `espiar_broker.py sin_admin`.
  3. Los datos: `inflate` de zlib (0x788260) se engancha para guardar los XML que el server lee
     (Product, Skill, StageReward, ItemTypeList) en `_trabajo/datos/` la primera vez que el
     juego los descomprime de `Data.dat`.

    from eda_original import lanzar;  lanzar()          # lo usa jugar.py
    py herramientas\eda_original.py control             # el armado de los XML (con su revés)
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sin_gameguard as SG                                    # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
DATOS = os.path.join(RAIZ, "_trabajo", "datos")
# raíz del XML → nombre del archivo (lo que lee servidor/juego.py)
XMLS = {"SHOP": "Product", "SKILLXML": "Skill", "STAGE_REWARDS": "StageReward",
        "ITEMTYPELIST": "ItemTypeList"}
INFLATE = 0x788260
INFLATE_BYTES = "8b44240483ec3885"           # el comienzo de inflate ya desempacado
BROKER = ([218, 145, 66, 187], 25000)
LOCAL = ([127, 0, 0, 1], 25900)

JS = r"""
'use strict';
const parches = %(parches)s, faltan_xml = %(xmls)s;
const quien = %(quien)s, aca = %(aca)s;
function hex(p, n) { return Array.from(new Uint8Array(p.readByteArray(n)))
                         .map(b => ('0' + b.toString(16)).slice(-2)).join(''); }

// --- 0. compatibilidad Direct3D 9 en Windows moderno (WDDM / NVIDIA) -----------------------
const d3d9Mod = Process.findModuleByName('d3d9.dll') || Module.load('d3d9.dll');
const c9 = d3d9Mod ? d3d9Mod.getExportByName('Direct3DCreate9') : null;
const c9ex = d3d9Mod ? d3d9Mod.getExportByName('Direct3DCreate9Ex') : null;

function patchDevice(pDev) {
    if (!pDev || pDev.isNull()) return;
    const devVtbl = pDev.readPointer();
    // 23: CreateTexture(this, Width, Height, Levels, Usage, Format, Pool, ppTexture, pSharedHandle)
    Interceptor.attach(devVtbl.add(23 * 4).readPointer(), {
        onEnter: function (args) {
            if (args[6].toInt32() === 1) { // D3DPOOL_MANAGED -> D3DPOOL_DEFAULT + D3DUSAGE_DYNAMIC
                args[6] = ptr(0);
                args[4] = ptr(args[4].toInt32() | 0x200);
            }
        }
    });
    // 25: CreateCubeTexture
    Interceptor.attach(devVtbl.add(25 * 4).readPointer(), {
        onEnter: function (args) {
            if (args[6].toInt32() === 1) {
                args[6] = ptr(0);
                args[4] = ptr(args[4].toInt32() | 0x200);
            }
        }
    });
    // 26: CreateVertexBuffer(this, Length, Usage, FVF, Pool, ppVertexBuffer, pSharedHandle)
    Interceptor.attach(devVtbl.add(26 * 4).readPointer(), {
        onEnter: function (args) {
            if (args[4].toInt32() === 1) {
                args[4] = ptr(0);
                args[2] = ptr(args[2].toInt32() | 0x200);
            }
        }
    });
    // 27: CreateIndexBuffer(this, Length, Usage, Format, Pool, ppIndexBuffer, pSharedHandle)
    Interceptor.attach(devVtbl.add(27 * 4).readPointer(), {
        onEnter: function (args) {
            if (args[4].toInt32() === 1) {
                args[4] = ptr(0);
                args[2] = ptr(args[2].toInt32() | 0x200);
            }
        }
    });
}

if (c9 && c9ex) {
    const fnEx = new NativeFunction(c9ex, 'int', ['uint', 'pointer'], 'stdcall');
    Interceptor.replace(c9, new NativeCallback(function (version) {
        const pOut = Memory.alloc(Process.pointerSize);
        const hr = fnEx(version, pOut);
        if (hr === 0) {
            const pD3D = pOut.readPointer();
            const d3dVtbl = pD3D.readPointer();
            Interceptor.attach(d3dVtbl.add(16 * 4).readPointer(), {
                onEnter: function (args) {
                    this.ppDev = args[6];
                },
                onLeave: function (retval) {
                    if (retval.toInt32() === 0 && this.ppDev) {
                        patchDevice(this.ppDev.readPointer());
                    }
                }
            });
            return pD3D;
        }
        return ptr(0);
    }, 'pointer', ['uint'], 'stdcall'));
}

// --- 2. la red ---------------------------------------------------------------------------
const ws2 = Process.findModuleByName('ws2_32.dll') || Module.load('ws2_32.dll');
Interceptor.attach(ws2.getExportByName('connect'), {onEnter(a) {
    const sa = a[1];
    if (sa.readU16() !== 2) return;
    const puerto = (sa.add(2).readU8() << 8) | sa.add(3).readU8();
    for (let i = 0; i < 4; i++) if (sa.add(4 + i).readU8() !== quien[0][i]) return;
    if (puerto !== quien[1]) return;
    sa.add(2).writeU8(aca[1] >> 8); sa.add(3).writeU8(aca[1] & 0xff);
    for (let i = 0; i < 4; i++) sa.add(4 + i).writeU8(aca[0][i]);
    send({t: 'red'});
}});

// --- 3. los datos -------------------------------------------------------------------------
// ⚠ la búsqueda es NATIVA (Memory.scanSync): Data.dat pasa por inflate en miles de bloques y una
//   búsqueda byte por byte en JavaScript dejaba el arranque trabado (medido: 22:23, el juego no
//   llegaba ni a conectarse). Sólo se copian a JS los bloques del XML que se está juntando.
function patron(txt) { return Array.from(txt).map(c => ('0' + c.charCodeAt(0).toString(16)).slice(-2)).join(' '); }
const juntando = {};                    // raíz → [ArrayBuffer…]
function cierre(p, largo, raiz) {       // fin del «</RAIZ>» en el bloque, o -1
    const m = Memory.scanSync(p, largo, patron('</' + raiz + '>'));
    return m.length ? m[0].address.sub(p).toInt32() + raiz.length + 3 : -1;
}
function terminar(raiz) {
    const partes = juntando[raiz];
    let total = 0; partes.forEach(b => total += b.byteLength);
    const todo = new Uint8Array(total); let k = 0;
    partes.forEach(b => { todo.set(new Uint8Array(b), k); k += b.byteLength; });
    send({t: 'xml', raiz: raiz}, todo.buffer);
    delete juntando[raiz]; delete faltan_xml[raiz];
}
function bloque(p, largo) {
    for (const raiz of Object.keys(faltan_xml)) {
        let desde = 0;
        if (juntando[raiz]) {
            // 🟡 un «</RAIZ>» partido entre dos bloques no se ve: el XML entero sale igual al
            //   aparecer en el bloque siguiente que lo traiga completo (no pasó con los 4 de acá)
            const f = cierre(p, largo, raiz);
            juntando[raiz].push(p.readByteArray(f >= 0 ? f : largo));
            if (f >= 0) terminar(raiz);
            continue;
        }
        let ini = -1;
        for (const m of Memory.scanSync(p, largo, patron('<' + raiz))) {   // «<SHOP» sí, «<SHOPPING» no
            const i = m.address.sub(p).toInt32();
            if (i + raiz.length + 1 >= largo) continue;
            const c = p.add(i + raiz.length + 1).readU8();
            if (c === 0x20 || c === 0x3e || c === 0x0d || c === 0x0a) { ini = i; break; }
        }
        if (ini < 0) continue;
        const resto = p.add(ini), lr = largo - ini;
        const f = cierre(resto, lr, raiz);
        juntando[raiz] = [resto.readByteArray(f >= 0 ? f : lr)];
        if (f >= 0) terminar(raiz);
    }
}
function engancharInflate() {
    Interceptor.attach(ptr(%(inflate)d), {
        onEnter(a) { this.s = a[0]; this.o = a[0].add(0xC).readPointer(); },
        onLeave(rv) {
            if (!Object.keys(faltan_xml).length) return;
            const largo = this.s.add(0xC).readPointer().sub(this.o).toInt32();
            if (largo > 0) bloque(this.o, largo);
        }
    });
    send({t: 'inflate'});
}

// --- 1. GameGuard (cuando ASProtect termina de desempacar) -------------------------------
const hechos = {}; const t0 = Date.now(); let inflate_puesto = false;
function ponerParches(desde) {          // devuelve cuántos faltan
    let faltan = 0;
    for (const [va, viejo, nuevo] of parches) {
        if (hechos[va]) continue;
        const p = ptr(va);
        let actual;
        try { actual = hex(p, viejo.length / 2); } catch (e) { faltan++; continue; }
        if (actual === viejo) {
            const b = []; for (let i = 0; i < nuevo.length; i += 2) b.push(parseInt(nuevo.substr(i, 2), 16));
            Memory.patchCode(p, b.length, c => c.writeByteArray(b));
            hechos[va] = true; send({t: 'parche', va: va, ms: Date.now() - t0, desde: desde});
        } else if (actual === nuevo) { hechos[va] = true; } else { faltan++; }
    }
    return faltan;
}
// ★ los parches tienen que estar ANTES de que corran (12-nov: en otras PCs salía «Game guard
//   error : 45» = el juez de 0x403606 corrió antes que el temporizador). Dos ganchos deterministas,
//   en el MISMO hilo del juego, cuando el código ya está desempacado:
//   · GetCommandLineA = el arranque del CRT del juego (antes de todo);
//   · SetWindowLongA desde 0x403601 = la instrucción de antes del juez (0x403606).
//   El temporizador queda de respaldo.
const k32 = Process.getModuleByName('kernel32.dll');
const u32 = Process.findModuleByName('user32.dll') || Module.load('user32.dll');
for (const [m, n] of [[k32, 'GetCommandLineA'], [k32, 'GetCommandLineW'], [u32, 'SetWindowLongA']]) {
    let f = null;
    try { f = m.getExportByName(n); } catch (e) { continue; }
    // ⚠ sin filtrar por quién llama: en el original las llamadas pasan por los stubs de ASProtect
    //   (la dirección de vuelta no es del juego). Alcanza con que los bytes ya sean los originales
    //   desempacados, que ponerParches verifica antes de escribir.
    Interceptor.attach(f, {onEnter() { if (Object.keys(hechos).length < parches.length) ponerParches(n); }});
}
const vuelta = setInterval(function () {
    const faltan = ponerParches('reloj');
    if (!inflate_puesto && Object.keys(faltan_xml).length) {
        try { if (hex(ptr(%(inflate)d), 8) === '%(inflate_bytes)s') { engancharInflate(); inflate_puesto = true; } }
        catch (e) {}
    }
    if (faltan === 0 && (inflate_puesto || !Object.keys(faltan_xml).length)) {
        clearInterval(vuelta); send({t: 'listo', ms: Date.now() - t0});
    }
    if (Date.now() - t0 > 60000) { clearInterval(vuelta); send({t: 'tiempo', hechos: hechos}); }
}, 2);
"""


# ★ si el exe limpio llega a una llamada que el desempacado no pudo resolver, salta a la TRAMPA
#   (0xD0000000 + sitio − 0x400000) y se cae: se avisa QUÉ sitio, para resolverlo (así encontró
#   Urek-Mazinoo el de 0x7EE13C, PR #1 del repo público).
JS_TRAMPA = r"""
Process.setExceptionHandler(function (d) {
    const eip = d.context.pc;
    if (eip.compare(ptr('0xD0000000')) >= 0 && eip.compare(ptr('0xD0600000')) < 0)
        send({t: 'trampa', sitio: eip.sub(ptr('0xD0000000')).add(0x400000).toInt32()});
    return false;
});
"""
# 🟡 para PROBAR en una PC coreana (página 949) lo que ve una en español (1252): EDA_SIMULAR_ACP=1252
JS_ACP = r"""
for (const n of ['GetACP', 'GetOEMCP']) Interceptor.attach(
    Process.getModuleByName('kernel32.dll').getExportByName(n), {onLeave(r) { r.replace(ptr(%d)); }});
"""


def faltantes():
    return {r: n for r, n in XMLS.items() if not os.path.exists(os.path.join(DATOS, n + ".xml"))}


def _avisar(t):
    print(t, flush=True)


def lanzar(esperar=True, avisar=_avisar, nombre="EDA.exe"):
    """Abre `_trabajo/juego/EDA.exe` con todo puesto. Devuelve el pid. Con `esperar`, se queda
    hasta que el juego se cierra (guardando los XML que vayan saliendo)."""
    import frida
    # nombre: "EDA.exe" (el original, con ASProtect) o "EDA_limpio.exe" (desempacado y sin
    #   GameGuard: los parches ya están en el archivo, y se reconocen como hechos)
    exe = os.path.join(JUEGO, nombre)
    if not os.path.exists(exe):
        raise SystemExit("⛔ no está %s — corré primero: py jugar.py --preparar \"C:\\ruta\\al\\cliente\"" % exe)
    os.makedirs(DATOS, exist_ok=True)
    parches = [[va, viejo, nuevo] for va, viejo, nuevo, _ in SG.RECETAS["limpio"]]
    js = JS % {"parches": json.dumps(parches), "xmls": json.dumps(faltantes()),
               "quien": json.dumps(BROKER), "aca": json.dumps(LOCAL), "inflate": INFLATE,
               "inflate_bytes": INFLATE_BYTES}
    js += JS_TRAMPA
    if os.environ.get("EDA_SIMULAR_ACP"):                  # p. ej. 1252 = una PC en español
        js += JS_ACP % int(os.environ["EDA_SIMULAR_ACP"])
    pid = frida.spawn([exe], cwd=JUEGO, stdio="pipe")
    ses = frida.attach(pid)
    sc = ses.create_script(js)
    estado = {"vivo": True}

    def msg(m, d):
        p = m.get("payload", m)
        if not isinstance(p, dict):
            avisar("  %s" % p)
            return
        if p.get("t") == "xml" and d:
            ruta = os.path.join(DATOS, XMLS[p["raiz"]] + ".xml")
            open(ruta, "wb").write(d)
            avisar("  ★ datos: %s (%d bytes)" % (os.path.basename(ruta), len(d)))
        elif p.get("t") == "tiempo":
            avisar("  ⛔ GameGuard: no se pudieron poner todos los parches (%s). ¿Es el EDA.exe de "
                   "2009 sin tocar? (md5 f0b12e6cddf3efdd0676b6491efe46be)" % p.get("hechos"))
        elif p.get("t") == "trampa":
            avisar("  ⛔ el juego llegó a una llamada de Windows SIN RESOLVER: sitio 0x%X. Abrí un issue "
                   "con este número (ver documentacion/APIS_A_MANO.md)." % p["sitio"])
        elif p.get("t") == "parche":
            avisar("  · parche 0x%X puesto (%s, %d ms)" % (p["va"], p.get("desde"), p["ms"]))
        elif p.get("t") == "listo":
            avisar("  ✅ GameGuard pasado (%d ms)" % p["ms"])

    sc.on("message", msg)
    ses.on("detached", lambda *a: estado.update(vivo=False))
    sc.load()
    frida.resume(pid)
    avisar("★ %s abierto (pid %d)" % (nombre, pid))
    open(os.path.join(RAIZ, "_trabajo", "multi_pids.txt"), "w").write(str(pid))
    if esperar:
        while estado["vivo"]:
            time.sleep(0.5)
    return pid


def control():
    """El armado de los XML por bloques, sin el juego: el JS se traduce a mano acá (la misma
    lógica) y se prueba con un XML partido en 3 bloques, y con su revés."""
    ok = []

    def chequear(n, c):
        print("  %s %s" % ("✅" if c else "⛔", n))
        ok.append(bool(c))
    faltan = {"SHOP": "Product"}
    juntando, salio = {}, {}

    def bloque(u):
        for raiz in list(faltan):
            if raiz in juntando:
                juntando[raiz].append(u)
            else:
                i = u.find(b"<" + raiz.encode())
                while i >= 0 and u[i + len(raiz) + 1:i + len(raiz) + 2] not in (b" ", b">", b"\r", b"\n"):
                    i = u.find(b"<" + raiz.encode(), i + 1)
                if i < 0:
                    continue
                juntando[raiz] = [u[i:]]
            f = juntando[raiz][-1].find(b"</" + raiz.encode() + b">")
            if f >= 0:
                juntando[raiz][-1] = juntando[raiz][-1][:f + len(raiz) + 3]
                salio[raiz] = b"".join(juntando.pop(raiz))
                del faltan[raiz]
    bloque(b"sin nada <SHOPPING> solo esto")
    chequear("★ el revés: un bloque con sólo «<SHOPPING» no empieza nada", "SHOP" not in juntando)
    xml = b'<SHOP><PRODUCTS NUM="1"><Product ID="1"/></PRODUCTS></SHOP>'
    for trozo in (b"basura <SHOPPING> " + xml[:10], xml[10:30], xml[30:] + b" mas basura"):
        bloque(trozo)
    chequear("un XML partido en 3 bloques (con «<SHOPPING» antes) sale entero",
             salio.get("SHOP") == xml)
    chequear("y ya no se busca más (faltan vacío)", not faltan)
    chequear("la receta de GameGuard tiene sus 4 parches", len(SG.RECETAS["limpio"]) == 4)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(control() if sys.argv[1:2] == ["control"] else (lanzar() and 0))
