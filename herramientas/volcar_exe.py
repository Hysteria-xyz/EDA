"""volcar_exe.py — saca de la MEMORIA la imagen desempacada de un exe que está corriendo.

Para qué: EDA.exe viene empaquetado con ASProtect (documentacion/MEDICIONES.md). En disco el código
está cifrado; una vez que arranca, ASProtect lo desarma entero en memoria. Esto lo copia de ahí.

    python herramientas/volcar_exe.py                 # busca EDA.exe corriendo
    python herramientas/volcar_exe.py --pid 1234
    python herramientas/volcar_exe.py --nombre ping.exe --salida _trabajo/control_ping

Sólo LEE (OpenProcess con QUERY_INFORMATION | VM_READ): no escribe un byte en el proceso.
Si el proceso corre como admin, hace falta correr esto como admin (lo dice y sale).

Deja en --salida (por defecto _trabajo/volcado/<hora>/):
  imagen.bin        la imagen tal cual está en memoria (base .. base+SizeOfImage); lo ilegible = ceros
  EDA_volcado.exe   la misma imagen con cabecera PE «de memoria» (raw = virtual), para leerla con
                    herramientas de exe. ⚠ NO corre: el punto de entrada sigue siendo el de ASProtect
                    y los imports no están reconstruidos.
  modulos.json      cada DLL cargada (nombre, ruta, base, tamaño): con esto se traducen los
                    punteros de la tabla de imports a nombres de función, sin el juego abierto
  regiones/         las zonas ejecutables FUERA de cualquier módulo (donde ASProtect deja sus stubs)
  informe.txt       qué se leyó, qué no, y la comparación con el archivo de disco
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import struct
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_NOACCESS, PAGE_GUARD = 0x01, 0x100
PAGE_EXEC = 0x10 | 0x20 | 0x40 | 0x80


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


k32.OpenProcess.restype = wt.HANDLE
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(wt.HMODULE), wt.DWORD,
                                       ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleFileNameExW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]


class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD),
                ("EntryPoint", ctypes.c_void_p)]


psapi.GetModuleInformation.argtypes = [wt.HANDLE, wt.HMODULE, ctypes.POINTER(MODULEINFO), wt.DWORD]


def buscar_pid(nombre):
    import subprocess
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", "IMAGENAME eq %s" % nombre],
                         capture_output=True, text=True, errors="replace").stdout
    pids = [int(l.split('","')[1]) for l in out.splitlines() if l.startswith('"')]
    return pids


def leer(h, dir_, n):
    buf = ctypes.create_string_buffer(n)
    leido = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(dir_), buf, n, ctypes.byref(leido))
    return buf.raw[:leido.value] if ok else None


def regiones(h, desde=0, hasta=0x7FFF0000):
    dir_ = desde
    mbi = MBI()
    while dir_ < hasta and k32.VirtualQueryEx(h, ctypes.c_void_p(dir_), ctypes.byref(mbi),
                                              ctypes.sizeof(mbi)):
        base = mbi.BaseAddress or 0
        yield base, mbi.RegionSize, mbi.State, mbi.Protect, mbi.Type
        dir_ = base + mbi.RegionSize


def modulos(h):
    arr = (wt.HMODULE * 1024)()
    nec = wt.DWORD()
    if not psapi.EnumProcessModulesEx(h, arr, ctypes.sizeof(arr), ctypes.byref(nec), 0x03):
        return []
    res = []
    for i in range(nec.value // ctypes.sizeof(wt.HMODULE)):
        ruta = ctypes.create_unicode_buffer(520)
        psapi.GetModuleFileNameExW(h, arr[i], ruta, 520)
        mi = MODULEINFO()
        psapi.GetModuleInformation(h, arr[i], ctypes.byref(mi), ctypes.sizeof(mi))
        res.append({"nombre": os.path.basename(ruta.value), "ruta": ruta.value,
                    "base": mi.lpBaseOfDll or 0, "tam": mi.SizeOfImage})
    return res


def secciones(pe_bytes):
    """[(nombre, va, vs, raw_ptr, raw_size, off_cabecera)] de una cabecera PE."""
    pe = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    n = struct.unpack_from("<H", pe_bytes, pe + 6)[0]
    so = struct.unpack_from("<H", pe_bytes, pe + 20)[0]
    off = pe + 24 + so
    out = []
    for i in range(n):
        nm, vs, va, rs, ro = struct.unpack_from("<8sIIII", pe_bytes, off + i * 40)
        out.append((nm.rstrip(b"\0").decode("latin1"), va, vs, ro, rs, off + i * 40))
    return pe, out


def parecido(a, b):
    n = min(len(a), len(b))
    return sum(1 for i in range(n) if a[i] == b[i]) / n if n else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int)
    ap.add_argument("--nombre", default="EDA.exe")
    ap.add_argument("--salida")
    a = ap.parse_args()

    pid = a.pid
    if not pid:
        pids = buscar_pid(a.nombre)
        if len(pids) != 1:
            sys.exit("[!] %d procesos «%s» corriendo: pasá --pid" % (len(pids), a.nombre))
        pid = pids[0]
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        err = ctypes.get_last_error()
        sys.exit("[!] no pude abrir el pid %d (error %d%s)" % (
            pid, err, ": acceso denegado → el juego corre como admin, hace falta UAC" if err == 5 else ""))

    mods = modulos(h)
    if not mods:
        sys.exit("[!] no pude listar los módulos (error %d)" % ctypes.get_last_error())
    prin = next((m for m in mods if m["nombre"].lower() == a.nombre.lower()), mods[0])
    base, tam = prin["base"], prin["tam"]

    salida = a.salida or os.path.join(RAIZ, "_trabajo", "volcado", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(os.path.join(salida, "regiones"), exist_ok=True)
    inf = []

    def log(s):
        print(s, flush=True)
        inf.append(s)

    log("pid %d · %s · base %08x · SizeOfImage %x" % (pid, prin["ruta"], base, tam))

    # 1) la imagen, página por página (lo que no se puede leer queda en ceros y se anota)
    img = bytearray(tam)
    no_leidas = 0
    for off in range(0, tam, 0x1000):
        b = leer(h, base + off, min(0x1000, tam - off))
        if b:
            img[off:off + len(b)] = b
        else:
            no_leidas += 1
    log("imagen: %d páginas, %d sin poder leer" % (tam // 0x1000, no_leidas))
    open(os.path.join(salida, "imagen.bin"), "wb").write(img)

    # 2) la cabecera: la de DISCO (ASProtect a veces ensucia la de memoria), pasada a raw = virtual
    disco = open(prin["ruta"], "rb").read()
    pe, secs = secciones(disco)
    hdr_tam = secs[0][1] if secs else 0x1000
    exe = bytearray(img)
    exe[:hdr_tam] = disco[:hdr_tam].ljust(hdr_tam, b"\0")
    for nm, va, vs, ro, rs, oh in secs:
        struct.pack_into("<II", exe, oh + 16, max(vs, 0), va)   # SizeOfRawData, PointerToRawData
    struct.pack_into("<I", exe, pe + 24 + 36, 0x1000)           # FileAlignment = SectionAlignment
    open(os.path.join(salida, os.path.splitext(prin["nombre"])[0] + "_volcado.exe"), "wb").write(exe)

    # 3) comparación con el disco, sección por sección: en un exe empaquetado la memoria
    #    tiene que DIFERIR del archivo; en uno normal tiene que coincidir casi entera
    for nm, va, vs, ro, rs, oh in secs:
        n = min(vs, rs)
        if n:
            log("  sección %-8s va=%07x  memoria vs disco: %5.1f%% igual"
                % (nm or "''", va, 100 * parecido(img[va:va + n], disco[ro:ro + n])))

    # 4) las DLL cargadas y las zonas ejecutables sueltas (los stubs del empaquetador)
    json.dump(mods, open(os.path.join(salida, "modulos.json"), "w", encoding="utf-8"), indent=1)
    log("módulos: %d" % len(mods))
    rangos = [(m["base"], m["base"] + m["tam"]) for m in mods]
    sueltas = 0
    for rb, rsz, st, pr, ty in regiones(h):
        if st != MEM_COMMIT or not (pr & PAGE_EXEC) or (pr & (PAGE_GUARD | PAGE_NOACCESS)):
            continue
        if any(lo <= rb < hi for lo, hi in rangos):
            continue
        b = leer(h, rb, rsz)
        if b:
            open(os.path.join(salida, "regiones", "%08x.bin" % rb), "wb").write(b)
            sueltas += 1
    log("zonas ejecutables fuera de módulos: %d" % sueltas)

    # 5) una muestra de texto legible: si está desempacado, tiene que haber MUCHO
    import re
    cadenas = re.findall(rb"[ -~]{8,}", bytes(img))
    log("cadenas legibles (8+ chars) en la imagen: %d (en el archivo de disco: %d)"
        % (len(cadenas), len(re.findall(rb"[ -~]{8,}", disco))))
    open(os.path.join(salida, "informe.txt"), "w", encoding="utf-8").write("\n".join(inf) + "\n")
    log("→ %s" % salida)


if __name__ == "__main__":
    main()
