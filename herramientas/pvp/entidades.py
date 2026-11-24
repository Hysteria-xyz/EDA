r"""entidades -- ★ PvP: qué hace el COMBATE adentro de cada juego (grupos, golpes, daño, vida, muerte), en vivo.

Engancha con Frida, SÓLO A LEER, los puntos de documentacion/PVP_SETENTITYGROUP.md §8 en los dos juegos de
dos_clientes.py. Antes de enganchar cada uno compara sus bytes en memoria con los de exe/EDA_limpio.exe (md5
0799387e): si uno no coincide, ese no se engancha y se avisa (otro exe).

    py herramientas\pvp\entidades.py mirar [segundos=300]     # → <sesión>\entidades.jsonl + lo importante en consola
    py herramientas\pvp\entidades.py resumen <entidades.jsonl>
    py herramientas\pvp\entidades.py control                  # los bytes de cada punto contra el exe (y su revés)

Lo que anota (cada línea con t = el reloj de alta precisión, el mismo de udp_combate.py y combate_auto.py):
  setentitygroup  el guion pidió SetEntityGroup(id, grupo)  (y si este juego es el máster)
  setgroup        CEntity::SetGroup: id, grupo, máscara +0x40 que queda        (también el que llega por red)
  golpe_red       0x554B70 ¿se acepta un golpe llegado por la red?: entidad, la otra, sus máscaras, el resultado (al)
  filtro_area     0x5596CA el filtro de grupo del daño de área: candidato y atacante, ¿lo descarta?
  filtro_agarre   0x55758A lo mismo para el agarre
  ondamaged       0x559940 el despacho al OnDamaged del guion: la entidad golpeada y su vida
  vida_red        0x58B4C4 llega por red la vida de otra entidad (sólo cuando cambia)
  sethp           0x560F00 SetHP (sólo cuando cambia)
  muerte/revive   0x55707D / 0x55493D
"""
import json
import os
import sys
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import dos_clientes as D                                     # noqa: E402

# dirección → (nombre, primeros 6 bytes en exe/EDA_limpio.exe)
PUNTOS = {
    0x6385F0: ("setentitygroup", "6aff64a10000"),
    0x560CD0: ("setgroup", "8b44240483f8"),
    0x554B70: ("golpe_red", "83ec18568bf1"),
    0x5596CA: ("filtro_area", "8b4640854740"),
    0x55758A: ("filtro_agarre", "8b4840854f40"),
    0x559940: ("ondamaged", "6aff64a10000"),
    0x58B4C4: ("vida_red", "89880c020000"),
    0x560F00: ("sethp", "8b4424048981"),
    0x55707D: ("muerte", "889e1d020000"),
    0x55493D: ("revive", "c6861d020000"),
}
SILENCIOSOS = ("vida_red", "sethp", "golpe_red")    # van al archivo; en consola sólo si cambian algo

JS = r"""
const k32 = Process.getModuleByName('kernel32.dll');
const qpc = new NativeFunction(k32.getExportByName('QueryPerformanceCounter'), 'int', ['pointer']);
const qpf = new NativeFunction(k32.getExportByName('QueryPerformanceFrequency'), 'int', ['pointer']);
const b8 = Memory.alloc(8); qpf(b8); const frec = b8.readU64().toNumber();
function ahora() { qpc(b8); return b8.readU64().toNumber() / frec * 1000.0; }
function u32(p, o) { try { return ptr(p).add(o).readU32(); } catch (e) { return null; } }
function f32(p, o) { try { return Math.round(ptr(p).add(o).readFloat() * 1000) / 1000; } catch (e) { return null; } }
function u8(p, o) { try { return ptr(p).add(o).readU8(); } catch (e) { return null; } }
function ent(p) {                       // +8 id · +0x40 máscara de grupo · +0x20C vida · +0x21D vivo
    if (p === null || ptr(p).isNull()) return null;
    return {id: u32(p, 8), grupo: u32(p, 0x40), vida: f32(p, 0x20C), vivo: u8(p, 0x21D)};
}
function pila(c, i) { try { return c.esp.add(4 * i).readU32(); } catch (e) { return null; } }
const PUNTOS = PUNTOS_JSON;
const ultimo = {};
function poner(dir, nombre, cb) {
    const a = ptr(dir);
    const hay = Array.from(new Uint8Array(a.readByteArray(6)), x => ('0' + x.toString(16)).slice(-2)).join('');
    if (hay !== PUNTOS[dir][1]) { send({q: 'aviso', t: ahora(), texto: nombre + ' ' + dir + ': bytes ' + hay + ' (no es el exe conocido): NO se engancha'}); return; }
    Interceptor.attach(a, cb);
}
poner('0x6385F0', 'setentitygroup', {onEnter() { const c = this.context;
    send({q: 'setentitygroup', t: ahora(), id: pila(c, 1), grupo: pila(c, 2), master: u8(c.ecx, 0x168)}); }});
poner('0x560CD0', 'setgroup', {onEnter() { this.e = this.context.ecx; this.g = pila(this.context, 1); },
    onLeave() { const e = ent(this.e); send({q: 'setgroup', t: ahora(), id: e && e.id, grupo: this.g, mascara: e && e.grupo}); }});
poner('0x554B70', 'golpe_red', {onEnter() { this.a = ent(this.context.ecx); this.b = ent(pila(this.context, 1)); },
    onLeave(r) { send({q: 'golpe_red', t: ahora(), entidad: this.a, otra: this.b, resultado: r.toInt32() & 0xff}); }});
poner('0x5596CA', 'filtro_area', {onEnter() { const c = this.context, v = ent(c.esi), at = ent(c.edi);
    send({q: 'filtro_area', t: ahora(), candidato: v, atacante: at,
          descarta: (v && at) ? ((v.grupo & at.grupo) !== 0) : null}); }});
poner('0x55758A', 'filtro_agarre', {onEnter() { const c = this.context, v = ent(c.eax), at = ent(c.edi);
    send({q: 'filtro_agarre', t: ahora(), objetivo: v, atacante: at,
          descarta: (v && at) ? ((v.grupo & at.grupo) !== 0) : null}); }});
poner('0x559940', 'ondamaged', {onEnter() { const c = this.context;
    const args = [1,2,3,4,5,6,7].map(i => pila(c, i));
    // arg1 = 🟡 el atacante (un puntero: se lee como entidad si se puede); arg2 = 🟡 el daño (float)
    let at = null; try { at = args[0] > 0x10000 ? ent(ptr(args[0])) : null; } catch (e) {}
    const dano = Math.round(Memory.alloc(4).writeU32(args[1] >>> 0).readFloat() * 1000) / 1000;
    send({q: 'ondamaged', t: ahora(), entidad: ent(c.ecx), atacante: at, dano: dano, args: args}); }});
poner('0x58B4C4', 'vida_red', {onEnter() { const c = this.context, id = u32(c.eax, 8);
    const v = Math.round(Memory.alloc(4).writeU32(c.ecx.toUInt32()).readFloat() * 1000) / 1000;
    if (ultimo['r' + id] !== v) { ultimo['r' + id] = v; send({q: 'vida_red', t: ahora(), id: id, vida: v}); } }});
poner('0x560F00', 'sethp', {onEnter() { const c = this.context, id = u32(c.ecx, 8);
    const v = Math.round(c.esp.add(4).readFloat() * 1000) / 1000;
    if (ultimo['h' + id] !== v) { ultimo['h' + id] = v; send({q: 'sethp', t: ahora(), id: id, vida: v}); } }});
poner('0x55707D', 'muerte', {onEnter() { send({q: 'muerte', t: ahora(), entidad: ent(this.context.esi)}); }});
poner('0x55493D', 'revive', {onEnter() { send({q: 'revive', t: ahora(), entidad: ent(this.context.esi)}); }});
send({q: 'listo', t: ahora()});
"""


def js():
    return JS.replace("PUNTOS_JSON", json.dumps({"0x%X" % k: v for k, v in PUNTOS.items()}))


def linea(p):
    q = p["q"]
    if q == "setentitygroup":
        return "SetEntityGroup(%s, %s) · máster=%s" % (p["id"], p["grupo"], p["master"])
    if q == "setgroup":
        return "SetGroup: id %s grupo %s → máscara %s" % (p["id"], p["grupo"], p["mascara"])
    if q in ("filtro_area", "filtro_agarre"):
        k = "candidato" if q == "filtro_area" else "objetivo"
        return "%s: atacante %s vs %s → %s" % (q, p["atacante"], p[k], "DESCARTA" if p["descarta"] else "pasa")
    if q == "golpe_red":
        return "golpe por red: %s ← %s → al=%s" % (p["entidad"], p["otra"], p["resultado"])
    if q == "ondamaged":
        return "OnDamaged: %s ← atacante %s · daño %s" % (p["entidad"], p.get("atacante"), p.get("dano"))
    if q in ("vida_red", "sethp"):
        return "%s: id %s vida %s" % (q, p["id"], p["vida"])
    if q in ("muerte", "revive"):
        return "%s: %s" % (q, p["entidad"])
    return json.dumps(p)


def mirar(segundos):
    import frida
    s = D.leer_sesion()
    if not s:
        raise SystemExit("⛔ no hay sesión de dos_clientes.py")
    ruta = os.path.join(s["carpeta"], "entidades.jsonl")
    f = open(ruta, "a", encoding="utf-8")
    candado = threading.Lock()
    sesiones = []
    for quien, pid in s["clientes"].items():
        ses = frida.attach(pid)
        sc = ses.create_script(js())

        def llego(m, _d, quien=quien, pid=pid):
            if m.get("type") != "send":
                if m.get("type") == "error":
                    print("  ⚠ %s: %s" % (quien, m.get("description")), flush=True)
                return
            p = m["payload"]
            p["juego"], p["pid"] = quien, pid
            with candado:
                f.write(json.dumps(p) + "\n")
                f.flush()
            if p["q"] == "listo":
                print("· %s enganchado" % quien, flush=True)
            elif p["q"] == "aviso":
                print("  ⚠ %s: %s" % (quien, p["texto"]), flush=True)
            elif p["q"] not in ("golpe_red",):
                print("  %s %s  %s" % (time.strftime("%H:%M:%S"), quien, linea(p)), flush=True)
        sc.on("message", llego)
        sc.load()
        sesiones.append(ses)
    print("· mirando %d s → %s (Ctrl+C corta)" % (segundos, ruta), flush=True)
    try:
        time.sleep(segundos)
    except KeyboardInterrupt:
        pass
    for ses in sesiones:
        try:
            ses.detach()
        except Exception:                                    # noqa: BLE001
            pass
    f.close()
    return 0


def resumen(ruta):
    import collections
    evs = [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]
    c = collections.Counter((e.get("juego"), e["q"]) for e in evs)
    for k, n in sorted(c.items(), key=lambda x: str(x)):
        print("  %-4s %-16s %6d" % (k[0], k[1], n))
    for e in evs:
        if e["q"] in ("setentitygroup", "setgroup", "filtro_area", "filtro_agarre", "ondamaged", "muerte", "revive",
                      "aviso") or (e["q"] in ("vida_red", "sethp")):
            print("  %10.0f %s %s" % (e["t"], e.get("juego"), linea(e)))
    return 0


def control():
    import pefile
    ok = []

    def chequear(nombre, cond):
        ok.append(bool(cond))
        print("  %s %s" % ("✅" if cond else "⛔", nombre))

    pe = pefile.PE(os.path.join(RAIZ, "exe", "EDA_limpio.exe"), fast_load=True)
    img, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    malos = [hex(va) for va, (_, b) in PUNTOS.items() if img[va - base:va - base + 6].hex() != b]
    chequear("los %d puntos tienen en exe/EDA_limpio.exe los bytes esperados" % len(PUNTOS), not malos)
    otro = bytes([img[0x560CD0 - base] ^ 0xFF]) + img[0x560CD0 - base + 1:0x560CD0 - base + 6]
    chequear("★ el revés: un byte distinto se detecta (no se engancharía)", otro.hex() != PUNTOS[0x560CD0][1])
    chequear("el JS lleva la tabla de bytes (la comprobación se hace en memoria, en el juego)",
             '"0x560CD0": ["setgroup", "8b44240483f8"]' in js())
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "mirar":
        return mirar(float(a[1]) if len(a) > 1 else 300)
    if cmd == "resumen" and len(a) > 1:
        return resumen(a[1])
    if cmd == "control":
        return control()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
