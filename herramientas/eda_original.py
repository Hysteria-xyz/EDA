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


def destino(texto):
    """«IP» o «IP:PUERTO» → ([a, b, c, d], puerto) para el desvío del connect. Un nombre (p. ej. un
    dominio) se resuelve acá, una vez: el juego recibe la IP."""
    import socket
    host, _, puerto = texto.strip().rpartition(":") if ":" in texto else (texto.strip(), "", "")
    ip = socket.gethostbyname(host)
    return [int(x) for x in ip.split(".")], int(puerto or LOCAL[1])


# ★ LOS BOTONES CLAN / MESSENGER / OPTIONS DEL LOBBY (13-nov). Medido en el exe: el lobby une sus
#   botones con `0x4DF900(evento 3, control, delegado)`; la barra de arriba sólo trae 1 Shop,
#   2 Inventory, 6 Select Character y 7 Exit: 3 Clan, 4 Messenger y 5 Options NO tienen función
#   (se iluminan y no hacen nada). Acá, cuando el lobby une el control 1 (`0x4F6061`), se unen
#   también el 3, el 4 y el 5 con el MISMO delegado (gestor 0x899624, función en +8, pantalla en
#   +0x10) pero con una función nuestra: manda al server un chat con un comando (/clan, /amigos,
#   /opciones), armado con las funciones del propio cliente (`0x7425D0` paquete, `0x7426F0`
#   comando, `0x7434F0` bytes, `0x7449F0` la red, `0x744790` mandar, `0x743390` liberar). El
#   server contesta en el chat (y con /opciones abre la ventana de opciones en esta PC).
BOTONES_JS = r"""
(function () {
    const B = Process.enumerateModules()[0].base;
    const VA = function (v) { return B.add(v - 0x400000); };
    const unir = new NativeFunction(VA(0x4df900), 'void', ['pointer', 'int', 'int', 'pointer'], 'thiscall');
    const pInit = new NativeFunction(VA(0x7425d0), 'pointer', ['pointer'], 'thiscall');
    const pCmd = new NativeFunction(VA(0x7426f0), 'void', ['pointer', 'uint32'], 'thiscall');
    const pBytes = new NativeFunction(VA(0x7434f0), 'uint8', ['pointer', 'pointer', 'uint32'], 'thiscall');
    const red = new NativeFunction(VA(0x7449f0), 'pointer', []);
    const mandar = new NativeFunction(VA(0x744790), 'void', ['pointer', 'pointer'], 'thiscall');
    const pFin = new NativeFunction(VA(0x743390), 'void', ['pointer'], 'thiscall');
    function chat(texto) {
        const largo = texto.length * 2;
        const cuerpo = Memory.alloc(13 + largo);
        cuerpo.writeU8(1);
        cuerpo.add(1).writeU32(0xffffffff);
        cuerpo.add(5).writeU32(0);
        cuerpo.add(9).writeU32(largo);
        for (let i = 0; i < texto.length; i++) cuerpo.add(13 + 2 * i).writeU16(texto.charCodeAt(i));
        const p = Memory.alloc(0x1100);
        pInit(p);
        pCmd(p, 0x100d);
        pBytes(p, cuerpo, 13 + largo);
        mandar(red(), p);
        pFin(p);
    }
    globalThis.__eda_chat = chat;
    const acciones = {3: '/clan', 4: '/messenger', 5: '/opciones'};
    const funciones = {};
    for (const k in acciones) {
        funciones[k] = new NativeCallback(function (pantalla, evento) {
            try { chat(acciones[k]); send({t: 'boton', boton: acciones[k]}); }
            catch (e) { send({t: 'boton', boton: acciones[k] + ' ERROR ' + e}); }
        }, 'void', ['pointer', 'pointer'], 'thiscall');
    }
    globalThis.__eda_botones = funciones;
    const sitio = VA(0x4f6061 + 5);
    Interceptor.attach(VA(0x4df900), {
        onEnter(args) {
            if (!this.returnAddress.equals(sitio)) return;
            this.lobby = this.context.ecx;
            this.delegado = Memory.dup(args[2], 0x18);
        },
        onLeave() {
            if (this.lobby === undefined) return;
            for (const k in funciones) {
                const d = Memory.dup(this.delegado, 0x18);
                d.add(8).writePointer(funciones[k]);
                unir(this.lobby, 3, parseInt(k), d);
            }
            send({t: 'boton', boton: 'lobby: Clan, Messenger y Options unidos'});
        }
    });
})();
"""

# ★ VENTA MÚLTIPLE en el Inventory del juego (14-nov). Medido con herramientas/exp_inventario.py:
#   la escena del Inventory está en el global 0x934554; la página elegida = control 0x2ee0 (+0x118 =
#   0x2ee1..0x2ee5) de la ventana 0x258; su grilla = control 0x2f44+100k de la ventana 0x262+10k; la
#   celda elegida = grilla+0x3e0 (cada clic la cambia, también con Ctrl); el ítem = celda+0x250
#   (+4 serial, +8 tipo); el rectángulo de la celda = floats +0x0c..+0x18 (relativo a la grilla).
#   «Sell» → Confirm llama 0x54a990(serial) (manda 0x1041). Esto:
#     · Ctrl+clic en un ítem de la bolsa lo MARCA / desmarca (se ve: EDA-Atajos dibuja un marco rojo
#       con las celdas que le pasa el lanzador en _trabajo/servidor/marcas.json);
#     · al confirmar «Sell» de cualquiera, manda un 0x1041 por CADA marcado (el server contesta un
#       0x1042 por cada uno, como con el Sell de siempre: el ítem sale de la grilla y el oro sube).
#   Las marcas se borran al vender, al cambiar de página o al salir del Inventory.
# ★ TECLAS EN VIVO (14-nov): la tabla de comandos de consola del exe (0x910ac0: nombre, función)
#   trae «Bind» = 0x422da0 (cdecl argc, argv): BORRA lo que tenía ese botón (input+0x28) y le
#   pone las acciones dadas (input+0x2c, como el rangebind 0 0 del autoexec.cfg). El lanzador mira
#   EDA-teclas.json y, si cambia, manda acá los botones cambiados; se aplican desde PeekMessage
#   (el hilo del juego, entre cuadros), no desde el hilo de Frida.
TECLAS_JS = r"""
(function () {
    Module.load('user32.dll');      // (al inyectar, el juego todavía no la cargó)
    const B = Process.enumerateModules()[0].base;
    const bind = new NativeFunction(B.add(0x422da0 - 0x400000), 'void', ['int', 'pointer'], 'mscdecl');
    let cola = [];
    let hilo = null;
    // ★ CONSOLA (14-nov): [0x92cf50]+0x200 = RunConsoleString(char*) (lo usa 0x404a00 con
    //   «ScreenGlowEnable 1»): las Options en vivo (volumen, niebla, sombras, brillo, mouse,
    //   alwaysfocused) y _trabajo/servidor/consola.txt.
    let comandos = [];
    function recibirConsola() {
        recv('consola', function (m) { comandos = comandos.concat(m.lineas); recibirConsola(); });
    }
    recibirConsola();
    function consola() {
        const lista = comandos; comandos = [];
        const run = new NativeFunction(B.add(0x92cf50 - 0x400000).readPointer().add(0x200).readPointer(),
                                       'void', ['pointer'], 'mscdecl');
        for (const l of lista) run(Memory.allocAnsiString(l));
        send({t: 'boton', boton: 'consola: ' + lista.length + ' comandos'});
    }
    function recibir() {
        recv('teclas', function (m) {
            cola = cola.concat(m.binds);
            send({t: 'boton', boton: 'teclas recibidas: ' + m.binds.length + ' (hilo ' + hilo + ')'});
            recibir();
        });
    }
    recibir();
    function aplicar() {
        const lista = cola; cola = [];
        for (const b of lista) {               // b = [dispositivo, botón, [acciones…]]
            const textos = [b[0], b[1]].concat(b[2]).map(t => Memory.allocAnsiString(t));
            const argv = Memory.alloc(4 * textos.length);
            textos.forEach((t, i) => argv.add(4 * i).writePointer(t));
            bind(textos.length, argv);
        }
        send({t: 'boton', boton: 'teclas en vivo: ' + lista.length + ' botones'});
    }
    for (const n of ['PeekMessageA']) {
        Interceptor.attach(Module.getExportByName('user32.dll', n), {
            onEnter() {
                const yo = Process.getCurrentThreadId();
                if (hilo === null) hilo = yo;          // el 1º que bombea mensajes = el del juego
                if (yo !== hilo) return;
                if (comandos.length) { try { consola(); } catch (e) { send({t: 'boton', boton: 'consola ERROR ' + e}); } }
                if (cola.length === 0) return;
                try { aplicar(); } catch (e) { send({t: 'boton', boton: 'teclas ERROR ' + e}); }
            }
        });
    }
})();
"""


def binds_de(teclas):
    """{(dispositivo, botón): [acciones]} de EDA-teclas.json (con la lógica de EDA-Teclas.py).
    teclas None = las de fábrica."""
    import importlib.util
    ruta = os.path.join(os.path.dirname(RAIZ), "EDA-Teclas.py")
    spec = importlib.util.spec_from_file_location("eda_teclas", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if teclas is None:
        teclas = m.por_defecto()
    juntas = {a: [a] + extra for a, _, _, _, extra in m.ACCIONES}
    r = {}
    for a, _, _, _, _ in m.ACCIONES:
        if a in m.DE_EDA:
            continue
        for cod in teclas.get(a, []):
            if not cod:
                continue
            clave = ("##mouse", "##Button %d" % int(cod[1:])) if cod[0] == "M" else ("##keyboard", "##%d" % int(cod[1:]))
            r.setdefault(clave, []).extend(juntas[a])
    return r


def lineas_opciones():
    """Las Options de EDA-opciones.json como comandos de consola (las mismas líneas del autoexec.cfg,
    con la lógica de EDA-Opciones.py). Pantalla completa / monitor: sólo al abrir el juego."""
    import importlib.util
    ruta = os.path.join(os.path.dirname(RAIZ), "EDA-Opciones.py")
    spec = importlib.util.spec_from_file_location("eda_opciones", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    texto = m.aplicar("", m.leer_opciones())
    return [l for l in texto.splitlines() if l.strip() and not l.startswith(('"windowed"', '"screen'))]


def leer_teclas_json():
    try:
        return json.load(open(os.path.join(os.path.dirname(RAIZ), "EDA-teclas.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ★ FOCO (14-nov). Medido en el exe: el WndProc (0x409a…) al perder el foco (WM_ACTIVATE /
#   WM_NCACTIVATE con wParam 0) marca [0x90de80] = 1 «pausa» y [0x90de7c] = 0, pausa el sonido y
#   suelta la entrada; al volver lo re-adquiere todo (el «tarda en volver»). En la stage además
#   CursorCenter (0x40b102) pone el mouse en el centro CADA cuadro y ClipCursor lo encierra.
#   Esto: (1) al WndProc le llega «sigues activo» salvo que la ventana esté MINIMIZADA (minimizado
#   se deja como el original, para no dibujar sin pantalla); (2) SetCursorPos / ClipCursor no hacen
#   nada si EDA no está al frente; (3) un monitor de Direct3D (Present y TestCooperativeLevel ≠ 0)
#   para el cierre medido el 14-nov 07:11 (ACCESS_VIOLATION en d3d9 desde DrawIndexedPrimitive).
FOCO_JS = r"""
(function () {
    Module.load('user32.dll');
    const B = Process.enumerateModules()[0].base;
    const VA = v => B.add(v - 0x400000);
    const u = n => Module.getExportByName('user32.dll', n);
    const frente = new NativeFunction(u('GetForegroundWindow'), 'pointer', [], 'stdcall');
    const minim = new NativeFunction(u('IsIconic'), 'int', ['pointer'], 'stdcall');
    const getWL = new NativeFunction(u('GetWindowLongA'), 'pointer', ['pointer', 'int'], 'stdcall');
    let ventana = null, proc = null;
    function delJuego() { return ventana !== null && frente().equals(ventana); }
    // (1) el WndProc: se engancha con la 1ª ventana que pasa por PeekMessageA
    Interceptor.attach(u('PeekMessageA'), {
        onEnter(a) { this.m = a[0]; },
        onLeave(r) {
            if (proc !== null || r.toInt32() === 0) return;
            const h = this.m.readPointer();
            if (h.isNull()) return;
            ventana = h;
            proc = getWL(h, -4);
            Interceptor.attach(proc, { onEnter(a) {
                const m = a[1].toInt32() & 0xffff, w = a[2].toUInt32();
                if (minim(a[0]) !== 0) return;
                if ((m === 0x6 && (w & 0xffff) === 0) || (m === 0x1c && w === 0) || (m === 0x86 && w === 0))
                    a[2] = ptr(m === 0x6 ? (w | 1) : 1);
            } });
            send({t: 'boton', boton: 'foco: WndProc ' + proc.sub(B).add(0x400000) + ' (EDA no se pausa sin foco)'});
        }
    });
    // (2) el mouse: sin EDA al frente, ni centrarlo ni encerrarlo
    const scp = u('SetCursorPos'), clip = u('ClipCursor');
    const scpO = new NativeFunction(scp, 'int', ['int', 'int'], 'stdcall');
    const clipO = new NativeFunction(clip, 'int', ['pointer'], 'stdcall');
    Interceptor.replace(scp, new NativeCallback(function (x, y) {
        return delJuego() ? scpO(x, y) : 1;
    }, 'int', ['int', 'int'], 'stdcall'));
    Interceptor.replace(clip, new NativeCallback(function (r) {
        return clipO(delJuego() ? r : ptr(0));
    }, 'int', ['pointer'], 'stdcall'));
    // (3) Direct3D: el dispositivo sale del renderer (0x77b360: ecx+0x508)
    let dev = null;
    Interceptor.attach(VA(0x77b360), { onEnter() {
        if (dev !== null) return;
        dev = this.context.ecx.add(0x508).readPointer();
        const vt = dev.readPointer();
        for (const [nom, off] of [['Present', 0x44], ['TestCooperativeLevel', 0x0c], ['Reset', 0x40]]) {
            let ultimo = 0;
            Interceptor.attach(vt.add(off).readPointer(), { onLeave(r) {
                const v = r.toUInt32();
                if (v !== ultimo) { ultimo = v; send({t: 'boton', boton: 'D3D ' + nom + ' = 0x' + v.toString(16)}); }
            } });
        }
        send({t: 'boton', boton: 'D3D vigilado'});
    } });
})();
"""


# ★ 14-nov: VOLCAR los textos de Data.dat (guiones Lua de las stages, XML) mientras se juega, para
#   buscar reglas como «al romper un objeto suelta una poción». Sólo si existe el archivo
#   _trabajo/servidor/volcar_guiones (vale para UNA apertura: se borra al abrir). Engancha `uncompress` de zlib
#   (`0x8157b0`: dest, *destLen, src, srcLen; los bloques de 7680 B del Softnyx File System) y
#   manda sólo los bloques de TEXTO → _trabajo/servidor/guiones_texto.txt (en orden: un archivo
#   partido en varios bloques queda seguido).
GUIONES_JS = r"""
(function () {
    const B = Process.enumerateModules()[0].base;
    let total = 0;
    Interceptor.attach(B.add(0x8157b0 - 0x400000), {
        onEnter(a) { this.d = a[0]; this.n = a[1]; },
        onLeave(r) {
            if (r.toInt32() !== 0 || total > 80e6) return;
            const n = this.n.readU32();
            if (n < 16) return;
            const m = Math.min(n, 512);
            const u = new Uint8Array(this.d.readByteArray(m));
            let malos = 0, altos = 0;
            for (let i = 0; i < m; i++) {
                const c = u[i];
                if (c < 9 || (c > 13 && c < 32 && c !== 27)) malos++;
                else if (c >= 0x80) altos++;
            }
            if (malos * 50 > m || altos * 4 > m) return;   // (no es texto)
            const datos = this.d.readByteArray(n);
            // ★ 14-nov: los EFECTOS (.fxf: «PropName: …», miles de bloques) llenaban el tope al
            //   arrancar, antes de entrar a una stage: se saltan
            const txt = String.fromCharCode.apply(null, new Uint8Array(datos, 0, Math.min(n, 4096)));
            if (txt.indexOf('PropName:') >= 0 || txt.indexOf('FxName:') >= 0 || txt.indexOf('GroupName:') >= 0) return;
            total += n;
            send({t: 'guion', n: n}, datos);
        }
    });
    send({t: 'guion_listo'});
})();
"""


INVENTARIO_JS = r"""
(function () {
    Module.load('user32.dll');      // (al inyectar, el juego todavía no la cargó)
    const B = Process.enumerateModules()[0].base;
    const VA = function (v) { return B.add(v - 0x400000); };
    const ventana = new NativeFunction(VA(0x7510f0), 'pointer', ['pointer', 'uint32'], 'thiscall');
    const control = new NativeFunction(VA(0x755200), 'pointer', ['pointer', 'uint32'], 'thiscall');
    const cuenta = new NativeFunction(VA(0x623e60), 'pointer', []);
    const pInit = new NativeFunction(VA(0x7425d0), 'pointer', ['pointer'], 'thiscall');
    const pCmd = new NativeFunction(VA(0x7426f0), 'void', ['pointer', 'uint32'], 'thiscall');
    const pBytes = new NativeFunction(VA(0x7434f0), 'uint8', ['pointer', 'pointer', 'uint32'], 'thiscall');
    const red = new NativeFunction(VA(0x7449f0), 'pointer', []);
    const mandar = new NativeFunction(VA(0x744790), 'void', ['pointer', 'pointer'], 'thiscall');
    const pFin = new NativeFunction(VA(0x743390), 'void', ['pointer'], 'thiscall');
    let marcas = {};            // serial → la CELDA (puntero) de la grilla
    let pagina = -1, firma = '';
    let cache = null;          // (los controles se buscan UNA vez por apertura del Inventory)
    function grilla() {
        const escena = VA(0x934554).readPointer();
        // ★ medido 14-nov: +0xdc = la pantalla del costado (4, 5, 6 = Shop / Inventory / Refinery, todas con la bolsa; 7 Skill)
        if (escena.isNull() || [4, 5, 6].indexOf(escena.add(0xdc).readU32()) < 0) { cache = null; return null; }
        if (cache === null || !cache.escena.equals(escena)) {
            const ui = escena.add(0x14).readPointer();
            cache = {escena: escena, ui: ui, pest: control(ventana(ui, 0x258), 0x2ee0), g: {}};
        }
        if (cache.pest.isNull()) return null;
        const k = cache.pest.add(0x118).readU32() - 0x2ee1;
        if (k < 0 || k > 4) return null;
        if (!cache.g[k]) cache.g[k] = control(ventana(cache.ui, 0x262 + 10 * k), 0x2f44 + 100 * k);
        if (cache.g[k].isNull()) return null;
        return {k: k, g: cache.g[k]};
    }
    let oculto = false;
    // ★ 14-nov: la SELECCIÓN NATIVA. Medido en el exe: cada casilla es un botón de un grupo de
    //   radio (grilla+0x3d8, `0x7604b0`; +8 = la elegida = grilla+0x3e0). Al elegir una, el grupo
    //   (`0x75f8a0`) le pone el byte +0x248 = 1 y se lo saca a la anterior; la casilla, al
    //   actualizarse (`0x75f0c0`), dibuja con +0x248 la imagen de ELEGIDA (+0x128, el marco
    //   celeste) en vez de la normal (+0x184) / la de mouse encima (+0x1e0, si +0x34).
    //   Para marcar VARIAS se pone ese mismo byte en cada casilla marcada: la dibuja el juego, con
    //   su marco, debajo de sus carteles y avisos. (Ya no hace falta la capa de EDA-Atajos.)
    function pintar(celda, si) {
        if (celda.isNull()) return;
        celda.add(0x248).writeU8(si ? 1 : 0);
        celda.add(0x244).writePointer(si ? celda.add(0x128)
            : celda.add(celda.add(0x34).readU8() ? 0x1e0 : 0x184));
    }
    function elegida() { const r = grilla(); return r === null ? null : r.g.add(0x3e0).readPointer(); }
    function repintar() {
        const sel = elegida();
        for (const s of Object.keys(marcas)) {
            const c = marcas[s];
            // (si la casilla ya no tiene ese ítem —se movió o se vendió— la marca se cae)
            const it = c.add(0x250).readPointer();
            if (it.isNull() || it.add(4).readU32() !== Number(s)) { delete marcas[s]; if (!sel || !c.equals(sel)) pintar(c, false); continue; }
            if (c.add(0x248).readU8() !== 1) pintar(c, true);
        }
    }
    function soltar() {                    // desmarca todo (menos la elegida por el juego)
        const sel = elegida();
        for (const s of Object.keys(marcas)) {
            const c = marcas[s];
            if (!sel || !c.equals(sel)) { try { pintar(c, false); } catch (e) { } }
        }
        marcas = {};
    }
    function avisar() {
        if (firma !== '[]') { firma = '[]'; send({t: 'marcas', celdas: []}); }   // (la capa vieja: vacía)
    }
    // ★ 14-nov (medido con exp_inventario3.py): GetAsyncKeyState desde el juego da siempre 0 con
    //   clics cortos. Se lee el MENSAJE del clic al sacarlo de la cola (PeekMessage, en el hilo del
    //   juego): WM_LBUTTONUP (0x202) trae en wParam MK_CONTROL (0x8) si Ctrl estaba apretado.
    //   120 ms después (la grilla ya eligió la celda) se marca o desmarca esa celda.
    let pendiente = 0, vueltas = 0, simple = 0, antes = null;
    // ★ BOTONES Clan / Options / Messenger de la barra de arriba en Shop/Inventory/Refinery/Skill:
    //   el juego no los une a nada (en el lobby los une BOTONES_JS). Se leen del clic (lParam =
    //   x, y en la pantalla de 800×600), medidos con las capturas del 14-nov.
    const BARRA = [[465, 539, '/clan'], [547, 621, '/opciones'], [629, 703, '/messenger']];
    function barra(msg) {
        const esc = VA(0x934554).readPointer();
        if (esc.isNull() || [4, 5, 6, 7].indexOf(esc.add(0xdc).readU32()) < 0) return;
        const l = msg.add(12).readU32(), x = l & 0xffff, y = l >>> 16;
        if (y < 8 || y > 58) return;
        for (const b of BARRA) {
            if (x >= b[0] && x <= b[1] && globalThis.__eda_chat) {
                globalThis.__eda_chat(b[2]);
                send({t: 'boton', boton: b[2] + ' (barra del costado)'});
            }
        }
    }
    // ★ un AVISO del juego abierto (medido 14-nov: [escena]+0x5c = 0x4de9d0 muestra la ventana
    //   [[escena+0xc]+0x98]; su byte +0xb = visible): con un aviso abierto no se dibujan los marcos
    let ventanaAviso = null, escAviso = null;
    function avisoAbierto(esc) {
        if (escAviso === null || !escAviso.equals(esc)) {
            escAviso = esc;
            const cfg = esc.add(0xc).readPointer();
            ventanaAviso = cfg.isNull() ? null : ventana(esc.add(0x14).readPointer(), cfg.add(0x98).readU32());
        }
        return ventanaAviso !== null && !ventanaAviso.isNull() && ventanaAviso.add(0xb).readU8() !== 0;
    }
    function revisar() {
        const esc0 = VA(0x934554).readPointer();
        const ahora = !esc0.isNull() && (!esc0.add(0x15c).readPointer().isNull() || avisoAbierto(esc0));
        if (ahora !== oculto) { oculto = ahora; avisar(); }
        const r = grilla();
        if (r === null || r.k !== pagina) {
            if (Object.keys(marcas).length) { if (r !== null) soltar(); marcas = {}; avisar(); }
            pagina = r === null ? -1 : r.k;
        }
        if (r === null) return;
        // un clic SIN Ctrl que elige otra casilla de la bolsa = selección nueva: se sueltan las
        // marcas (como en Windows). Un clic en «Sell» u otro botón no cambia la elegida: quedan.
        if (simple !== 0 && Date.now() >= simple) {
            simple = 0;
            const sel = r.g.add(0x3e0).readPointer();
            if (Object.keys(marcas).length && antes !== null && !sel.equals(antes)) {
                soltar();
                send({t: 'boton', boton: 'marcas: 0'});
            }
        }
        if (pendiente === 0 || Date.now() < pendiente) { repintar(); return; }
        pendiente = 0;
        const celda = r.g.add(0x3e0).readPointer();
        if (celda.isNull() || celda.add(0x250).readPointer().isNull()) { repintar(); return; }
        const serial = celda.add(0x250).readPointer().add(4).readU32();
        // la primera marca con Ctrl incluye la casilla que ya estaba elegida (como en Windows)
        if (!Object.keys(marcas).length && antes !== null && !antes.isNull() && !antes.equals(celda)) {
            const it = antes.add(0x250).readPointer();
            if (!it.isNull()) marcas[it.add(4).readU32()] = antes;
        }
        if (marcas[serial]) { delete marcas[serial]; pintar(celda, false); }
        else marcas[serial] = celda;
        repintar();
        send({t: 'boton', boton: 'marcas: ' + Object.keys(marcas).length});
    }
    let hiloInv = null;
    // (medido con exp_inventario4.py: el hilo del juego usa PeekMessageA; otro hilo usa la W)
    for (const n of ['PeekMessageA']) {
        Interceptor.attach(Module.getExportByName('user32.dll', n), {
            onEnter(args) { this.msg = args[0]; },
            onLeave(ret) {
                const yo = Process.getCurrentThreadId();
                if (hiloInv === null) hiloInv = yo;
                if (yo !== hiloInv) return;
                try {
                    const m = ret.toInt32() !== 0 ? this.msg.add(4).readU32() : 0;
                    if (m === 0x201) { antes = elegida(); }        // (la elegida ANTES del clic)
                    if (m === 0x202) {
                        if ((this.msg.add(8).readU32() & 0x8) !== 0) pendiente = Date.now() + 120;
                        else { simple = Date.now() + 120; barra(this.msg); }
                    }
                    if (pendiente > 0 || simple > 0 || (++vueltas % 4) === 0) revisar();
                } catch (e) { if (!globalThis.__eda_err) { globalThis.__eda_err = 1; send({t: 'boton', boton: 'marcas ERROR ' + e}); } }
            }
        });
    }
    function vender(serial) {
        const cuerpo = Memory.alloc(8);
        cuerpo.writeU32(cuenta().add(0x2b8).readU32());
        cuerpo.add(4).writeU32(serial);
        const p = Memory.alloc(0x1100);
        pInit(p);
        pCmd(p, 0x1041);
        pBytes(p, cuerpo, 8);
        mandar(red(), p);
        pFin(p);
    }
    Interceptor.attach(VA(0x54a990), {
        onEnter(args) { this.serial = args[0].toUInt32(); },
        onLeave() {
            const otros = Object.keys(marcas).map(Number).filter(s => s !== this.serial);
            for (const s of otros) { try { vender(s); } catch (e) { } }
            if (otros.length) send({t: 'boton', boton: 'venta múltiple: ' + (otros.length + 1) + ' ítems'});
            try { soltar(); } catch (e) { }
            marcas = {};
            avisar();
        }
    });
})();
"""

def lanzar(esperar=True, avisar=_avisar, nombre="EDA.exe", server=None):
    """Abre `_trabajo/juego/EDA.exe` con todo puesto. Devuelve el pid. Con `esperar`, se queda
    hasta que el juego se cierra (guardando los XML que vayan saliendo). `server` = ([IP], puerto)
    adonde va el juego (por defecto este PC, 127.0.0.1:25900)."""
    import frida
    # nombre: "EDA.exe" (el original, con ASProtect) o "EDA_limpio.exe" (desempacado y sin
    #   GameGuard: los parches ya están en el archivo, y se reconocen como hechos)
    exe = os.path.join(JUEGO, nombre)
    if not os.path.exists(exe):
        raise SystemExit("⛔ no está %s — corré primero: py jugar.py --preparar \"C:\\ruta\\al\\cliente\"" % exe)
    os.makedirs(DATOS, exist_ok=True)
    parches = [[va, viejo, nuevo] for va, viejo, nuevo, _ in SG.RECETAS["limpio"]]
    js = JS % {"parches": json.dumps(parches), "xmls": json.dumps(faltantes()),
               "quien": json.dumps(BROKER), "aca": json.dumps(server or LOCAL), "inflate": INFLATE,
               "inflate_bytes": INFLATE_BYTES}
    js += JS_TRAMPA
    if os.environ.get("EDA_SIMULAR_ACP"):                  # p. ej. 1252 = una PC en español
        js += JS_ACP % int(os.environ["EDA_SIMULAR_ACP"])
    # ★ la d3d9.dll también desvía el connect si su ini tiene [red] server= (MEDICIONES §44): se le
    #   pasa EDA_SERVER (que manda sobre el ini) con el MISMO destino, así los dos dicen lo mismo
    dest = server or LOCAL
    env = {"EDA_SERVER": "%s:%d" % (".".join(map(str, dest[0])), dest[1])}
    if nombre != "EDA.exe" and os.environ.get("EDA_SIN_BOTONES") != "1":
        # ★ (14-nov) los botones, la selección múltiple y el foco los hace la d3d9.dll ([mazino], MEDICIONES §57):
        #   llegan a todos con el launcher. Acá quedan sólo para medir sin la dll (EDA_FRIDA_MEJORAS=1); con
        #   las dos a la vez se duplicarían (dos ventas por ítem marcado)
        if os.environ.get("EDA_FRIDA_MEJORAS") == "1":
            js += BOTONES_JS
            js += INVENTARIO_JS
            js += FOCO_JS
        js += TECLAS_JS                                # (teclas / Options en vivo de los paneles de Python)
        bandera = os.path.join(RAIZ, "_trabajo", "servidor", "volcar_guiones")
        if os.path.exists(bandera):                    # (una sola apertura: la bandera se borra)
            os.remove(bandera)
            salida = os.path.join(RAIZ, "_trabajo", "servidor", "guiones_texto.txt")
            if os.path.exists(salida):
                os.remove(salida)
            js += GUIONES_JS
    pid = frida.spawn([exe], cwd=JUEGO, stdio="pipe", env=env)
    ses = frida.attach(pid)
    sc = ses.create_script(js)
    estado = {"vivo": True}

    def msg(m, d):
        if m.get("type") == "error":                       # un error del JS: que se vea
            avisar("  ⛔ JS: %s (%s:%s)" % (m.get("description"), m.get("lineNumber"), m.get("columnNumber")))
            return
        p = m.get("payload", m)
        if not isinstance(p, dict):
            avisar("  %s" % p)
            return
        if p.get("t") == "marcas":                         # → EDA-Atajos dibuja los marcos
            try:
                ruta = os.path.join(RAIZ, "_trabajo", "servidor", "marcas.json")
                with open(ruta + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(p.get("celdas", []), f)
                os.replace(ruta + ".tmp", ruta)
            except OSError:
                pass
            return
        if p.get("t") == "guion" and d:                  # ★ un bloque de texto de Data.dat
            with open(os.path.join(RAIZ, "_trabajo", "servidor", "guiones_texto.txt"), "ab") as f:
                f.write(d)
            return
        if p.get("t") == "guion_listo":
            avisar("  ★ volcando los textos de Data.dat (guiones de stage)")
            return
        if p.get("t") == "boton":
            avisar("  · botón %s" % p.get("boton"))
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
        ruta_o = os.path.join(os.path.dirname(RAIZ), "EDA-opciones.json")
        ruta_c = os.path.join(RAIZ, "_trabajo", "servidor", "consola.txt")
        visto_o = os.path.getmtime(ruta_o) if os.path.exists(ruta_o) else 0
        ruta_t = os.path.join(os.path.dirname(RAIZ), "EDA-teclas.json")
        visto = os.path.getmtime(ruta_t) if os.path.exists(ruta_t) else 0
        antes = leer_teclas_json()
        while estado["vivo"]:
            time.sleep(0.5)
            try:                                       # ★ las teclas cambiadas: al juego, en vivo
                m = os.path.getmtime(ruta_t) if os.path.exists(ruta_t) else 0
                if m != visto and nombre != "EDA.exe":
                    visto = m
                    ahora = leer_teclas_json()
                    if ahora is not None:
                        viejo, nuevo = binds_de(antes), binds_de(ahora)
                        cambios = [[d, b, nuevo.get((d, b), [])] for (d, b) in set(viejo) | set(nuevo)
                                   if viejo.get((d, b)) != nuevo.get((d, b))]
                        if cambios:
                            sc.post({"type": "teclas", "binds": cambios})
                            avisar("  · teclas cambiadas en vivo: %d botones" % len(cambios))
                        antes = ahora
            except Exception as error:                 # noqa: BLE001
                avisar("  ⛔ teclas en vivo: %r" % error)
            try:                                       # ★ las Options guardadas: al juego, en vivo
                m = os.path.getmtime(ruta_o) if os.path.exists(ruta_o) else 0
                if m != visto_o and nombre != "EDA.exe":
                    visto_o = m
                    lineas = lineas_opciones()
                    if lineas:
                        sc.post({"type": "consola", "lineas": lineas})
                        avisar("  · options en vivo: %d" % len(lineas))
                if os.path.exists(ruta_c) and nombre != "EDA.exe":
                    lineas = [l.strip() for l in open(ruta_c, encoding="utf-8") if l.strip()]
                    os.remove(ruta_c)
                    sc.post({"type": "consola", "lineas": lineas})
                    avisar("  · consola: %s" % " | ".join(lineas))
            except Exception as error:                 # noqa: BLE001
                avisar("  ⛔ options en vivo: %r" % error)
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
