r"""vida -- ★ PvP, etapa 0.2: encontrar la VIDA (HP) de cada jugador en la memoria de cada juego y mirarla cambiar.

Nadie la ubicó todavía: MEDICIONES §34 la leyó del HUD («HP 126,6/126,6»). Es un buscador de valores de dos
pasadas, sólo LECTURA (`ReadProcessMemory`, con lo de `herramientas/buscar_en_memoria.py`): no escribe ni frena
el juego.

    py herramientas\pvp\vida.py buscar  A 126.6        # 1ª pasada: cada float32 ≈ 126,6 (±0,05) en el juego A
    py herramientas\pvp\vida.py filtrar A 110.2        # después de un golpe: quedan los que AHORA valen 110,2
    py herramientas\pvp\vida.py mirar [segundos=120]   # los candidatos de A y B, cada cambio con su hora
    py herramientas\pvp\vida.py control                # el control (con su revés), sobre este mismo proceso

A / B = los juegos de `dos_clientes.py` (o un pid). `--tipo i32` busca enteros en vez de float32. `--nombre X`
guarda/filtra un conjunto aparte (p. ej. `--nombre rui_en_kai` = la vida de rui vista desde el juego de kai).
Los candidatos quedan en <base>\vida_<pid>_<nombre>.json; `mirar` los mira todos y escribe vida.jsonl en la
carpeta de la sesión.

Para qué (PVP_MEDICIONES.md §2): buscar la vida de rui EN EL JUEGO DE rui y también EN EL JUEGO DE kai (su copia
remota). Si al pegarle kai a rui cambian las dos, y en qué orden, dice quién decide el daño.
"""
import ctypes
import json
import os
import struct
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import buscar_en_memoria as M                                # noqa: E402
import dos_clientes as D                                     # noqa: E402

k32 = M.k32
ESCRIBIBLE = (0x04, 0x08, 0x40, 0x80)                         # RW, WRITECOPY, EXECUTE_RW, EXECUTE_WRITECOPY
TOPE_CANDIDATOS = 200000


def resolver(quien):
    if quien.isdigit():
        return int(quien)
    s = D.leer_sesion()
    if not s or quien not in s.get("clientes", {}):
        raise SystemExit("⛔ no hay sesión de dos_clientes.py con el juego %s (o pasá un pid)" % quien)
    return s["clientes"][quien]


def abrir(pid):
    h = k32.OpenProcess(0x0410, False, pid)                  # QUERY_INFORMATION | VM_READ
    if not h:
        raise SystemExit("⛔ no pude abrir el proceso %d" % pid)
    return h


def leer(h, va, n):
    b = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t(0)
    if k32.ReadProcessMemory(h, ctypes.c_void_p(va), b, n, ctypes.byref(got)) and got.value == n:
        return b.raw
    return None


def valor(raw, tipo):
    return struct.unpack("<f" if tipo == "f32" else "<i", raw)[0]


def alto16(f):
    return struct.unpack("<I", struct.pack("<f", f))[0] >> 16


def patrones(objetivo, tol, tipo):
    """Los bytes a buscar. float32: los 16 bits ALTOS de los floats en [objetivo±tol] (para un float positivo el
    entero de sus bits crece con él), en el offset +2; después se mira el float entero. i32: el número exacto."""
    if tipo == "i32":
        return [(struct.pack("<i", int(round(objetivo))), 0)]
    lo, hi = sorted((alto16(objetivo - tol), alto16(objetivo + tol)))
    return [(struct.pack("<H", x), 2) for x in range(lo, hi + 1)]


def coincide(v, objetivo, tol, tipo):
    return v == int(round(objetivo)) if tipo == "i32" else abs(v - objetivo) <= tol


def buscar(pid, objetivo, tol=0.05, tipo="f32", tope=0x7FFFFFFEFFFF):
    h = abrir(pid)
    hallados = []
    try:
        pats = patrones(objetivo, tol, tipo)
        for base, tam, prot in M.regiones(h, tope):
            if (prot & 0xFF) not in ESCRIBIBLE:
                continue
            off = 0
            while off < tam:
                n = min(1 << 24, tam - off)
                b = ctypes.create_string_buffer(n)
                got = ctypes.c_size_t(0)
                if k32.ReadProcessMemory(h, ctypes.c_void_p(base + off), b, n, ctypes.byref(got)) and got.value:
                    d = b.raw[:got.value]
                    for pat, corr in pats:
                        i = d.find(pat)
                        while i != -1:
                            ini = i - corr
                            va = base + off + ini
                            if ini >= 0 and va % 4 == 0 and ini + 4 <= len(d):
                                v = valor(d[ini:ini + 4], tipo)
                                if coincide(v, objetivo, tol, tipo):
                                    hallados.append(va)
                            i = d.find(pat, i + 1)
                    if len(hallados) > TOPE_CANDIDATOS:
                        raise SystemExit("⛔ más de %d candidatos: probá con un valor menos común" % TOPE_CANDIDATOS)
                off += n
    finally:
        k32.CloseHandle(h)
    return sorted(set(hallados))


def filtrar(pid, candidatos, objetivo, tol=0.05, tipo="f32"):
    h = abrir(pid)
    try:
        quedan = []
        for va in candidatos:
            raw = leer(h, va, 4)
            if raw and coincide(valor(raw, tipo), objetivo, tol, tipo):
                quedan.append(va)
        return quedan
    finally:
        k32.CloseHandle(h)


def ruta_candidatos(pid, nombre="vida"):
    return os.path.join(D.BASE, "vida_%d_%s.json" % (pid, nombre))


def guardar(pid, cand, tipo, objetivo, nombre="vida"):
    os.makedirs(D.BASE, exist_ok=True)
    json.dump({"pid": pid, "nombre": nombre, "tipo": tipo, "ultimo": objetivo, "candidatos": cand},
              open(ruta_candidatos(pid, nombre), "w", encoding="utf-8"))


def mostrar(pid, cand, tipo):
    h = abrir(pid)
    try:
        mods = M.modulos(h)
        for va in cand[:20]:
            raw = leer(h, va, 4)
            print("    0x%08X = %s   (%s)" % (va, "?" if raw is None else round(valor(raw, tipo), 3), M.donde(mods, va)))
        if len(cand) > 20:
            print("    … y %d más" % (len(cand) - 20))
    finally:
        k32.CloseHandle(h)


def mirar(segundos, paso=0.05):
    s = D.leer_sesion()
    if not s:
        raise SystemExit("⛔ no hay sesión de dos_clientes.py")
    import glob
    vigilados = []
    for quien, pid in s["clientes"].items():
        rutas = sorted(glob.glob(os.path.join(D.BASE, "vida_%d_*.json" % pid)))
        if not rutas:
            print("· %s (pid %d): sin candidatos (primero: vida.py buscar %s <valor>)" % (quien, pid, quien))
        for r in rutas:
            c = json.load(open(r, encoding="utf-8"))
            et = "%s/%s" % (quien, c.get("nombre", "vida"))
            if len(c["candidatos"]) > 64:
                print("· %s: %d candidatos; miro los primeros 64 (conviene filtrar más)" % (et, len(c["candidatos"])))
            vigilados.append((et, pid, abrir(pid), c["tipo"], c["candidatos"][:64]))
    if not vigilados:
        return 1
    ruta = os.path.join(s["carpeta"], "vida.jsonl")
    f = open(ruta, "a", encoding="utf-8")
    ultimo = {}
    t0 = time.time()
    print("· mirando %d s (cada cambio va a %s); Ctrl+C para cortar" % (segundos, ruta))
    try:
        while time.time() - t0 < segundos:
            for quien, pid, h, tipo, cand in vigilados:
                for va in cand:
                    raw = leer(h, va, 4)
                    v = None if raw is None else round(valor(raw, tipo), 3)
                    k = (quien, va)
                    if ultimo.get(k, "∅") != v:
                        if k in ultimo:
                            t = time.time()
                            print("  %s %s 0x%08X  %s → %s" % (time.strftime("%H:%M:%S", time.localtime(t))
                                                              + ".%03d" % int(t % 1 * 1000), quien, va, ultimo[k], v))
                            f.write(json.dumps({"t": t, "juego": quien, "pid": pid, "va": va, "antes": ultimo[k],
                                                "ahora": v}) + "\n")
                            f.flush()
                        ultimo[k] = v
            time.sleep(paso)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()
        for _, _, h, _, _ in vigilados:
            k32.CloseHandle(h)
    return 0


def control():
    ok = []

    def chequear(nombre, cond):
        ok.append(bool(cond))
        print("  %s %s" % ("✅" if cond else "⛔", nombre))

    yo = os.getpid()
    arr = (ctypes.c_float * 4)(4242.3, 1.0, 4242.3, 7.0)
    a0, a2 = ctypes.addressof(arr), ctypes.addressof(arr) + 8
    c = buscar(yo, 4242.3)
    chequear("encuentra los dos float32 ≈ 4242,3 de este proceso", a0 in c and a2 in c)
    chequear("★ el revés: no da el 1,0 de al lado como candidato", ctypes.addressof(arr) + 4 not in c)
    arr[0] = 4100.5
    q = filtrar(yo, [a0, a2], 4100.5)
    chequear("filtrar: queda sólo el que cambió a 4100,5", q == [a0])
    chequear("★ el revés: con un valor que nadie tiene no queda ninguno", filtrar(yo, [a0, a2], 9.75) == [])
    pats = patrones(126.6, 0.05, "f32")
    chequear("126,6 ±0,05 cae en uno o dos patrones de 16 bits (búsqueda rápida)", 1 <= len(pats) <= 2)
    ent = (ctypes.c_int * 2)(987654, 3)
    ci = buscar(yo, 987654, tipo="i32")
    chequear("--tipo i32: encuentra el entero exacto", ctypes.addressof(ent) in ci)
    chequear("★ el revés: --tipo i32 no confunde 987655", ctypes.addressof(ent) not in buscar(yo, 987655, tipo="i32"))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    tipo = "i32" if "--tipo" in a and a[a.index("--tipo") + 1:a.index("--tipo") + 2] == ["i32"] else "f32"
    nombre = "vida"
    if "--nombre" in a and a.index("--nombre") + 1 < len(a):
        nombre = a[a.index("--nombre") + 1]
        if not nombre.replace("_", "").isalnum():
            raise SystemExit("⛔ --nombre: sólo letras, números y _")
        del a[a.index("--nombre"):a.index("--nombre") + 2]
    a = [x for x in a if x not in ("--tipo", "i32", "f32")]
    cmd = a[0] if a else ""
    if cmd == "control":
        return control()
    if cmd == "mirar":
        return mirar(float(a[1]) if len(a) > 1 else 120)
    if cmd in ("buscar", "filtrar") and len(a) == 3:
        pid, obj = resolver(a[1]), float(a[2].replace(",", "."))
        if cmd == "buscar":
            cand = buscar(pid, obj, tipo=tipo, tope=0x80000000)
        else:
            try:
                prev = json.load(open(ruta_candidatos(pid, nombre), encoding="utf-8"))
            except OSError:
                raise SystemExit("⛔ primero: vida.py buscar %s <valor> --nombre %s" % (a[1], nombre))
            tipo = prev["tipo"]
            cand = filtrar(pid, prev["candidatos"], obj, tipo=tipo)
        guardar(pid, cand, tipo, obj, nombre)
        print("· %s/%s (pid %d): %d candidatos para %s" % (a[1], nombre, pid, len(cand), obj))
        mostrar(pid, cand, tipo)
        return 0 if cand else 1
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
