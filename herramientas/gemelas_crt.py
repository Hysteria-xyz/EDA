r"""gemelas_crt -- las trampas de la CRT de EDA, resueltas por su GEMELA en msvcr71.dll (13-nov).

El exe de EDA se compiló con Visual C++ 7.1 (la firma «Rich» del exe: build 3077, más algunos objetos
de VC 8). Su biblioteca de C (la CRT, `0x7C0000…0x800000`) es la de VC 7.1, enlazada adentro.
`msvcr71.dll` es ESA MISMA biblioteca compilada como dll, y tiene sus importaciones con nombre.

La idea: alrededor de cada llamada a Windows, el código de la CRT es casi el mismo en el exe y en la
dll (mismo fuente, mismo compilador). Se toman las instrucciones de ANTES y de DESPUÉS de la trampa,
sin las direcciones (que cambian), y se buscan entre todas las `call dword ptr [IAT]` de msvcr71.dll.
Si una sola coincide claramente, su importación es la respuesta.

    py herramientas\gemelas_crt.py control     # ★ sobre los sitios de la CRT YA resueltos: tiene que
                                               #   acertar (y el revés: un sitio fuera de la CRT no
                                               #   tiene gemela)
    py herramientas\gemelas_crt.py             # las trampas de la CRT → filas candidatas

La dll de referencia: `_trabajo/exe_nuevo/ref/msvcr71.dll` (copia de la que traen los clientes de
R2Beat 2013, md5 86f1895a…). Sólo LEE.
"""
import os
import re
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import contar_piezas as cp                                    # noqa: E402

REF = os.path.join(RAIZ, "_trabajo", "exe_nuevo", "ref", "msvcr71.dll")
CRT = (0x7C0000, 0x800000)
ANTES, DESPUES = 10, 8           # cuántas instrucciones se comparan a cada lado
MINIMO = 11                      # coincidencias exactas para aceptar
VENTAJA = 3                      # y por cuánto le tiene que ganar a la segunda API distinta
MD = Cs(CS_ARCH_X86, CS_MODE_32)
NUM = re.compile(r"0x[0-9a-f]+")


def forma(i):
    """La instrucción sin direcciones: los números grandes (direcciones, destinos) se vuelven «A»."""
    if i.mnemonic in ("call", "jmp") or i.mnemonic.startswith("j"):
        if i.op_str.startswith("0x"):
            return i.mnemonic + " T"
    return i.mnemonic + " " + NUM.sub(lambda m: m.group() if int(m.group(), 16) < 0x10000 else "A", i.op_str)


class Imagen:
    def __init__(self, img, base):
        self.img, self.base = img, base

    def antes(self, va, n=ANTES):
        """Las n instrucciones que TERMINAN justo en va (se busca un arranque que caiga ahí)."""
        for atras in range(0x40, 0x10, -1):
            ins, a = [], va - atras
            for i in MD.disasm(self.img[a - self.base:va - self.base], a):
                ins.append(i)
            if ins and ins[-1].address + ins[-1].size == va:
                return [forma(i) for i in ins[-n:]]
        return []

    def despues(self, va, n=DESPUES):
        return [forma(i) for i, _ in zip(MD.disasm(self.img[va - self.base:va - self.base + 0x60], va), range(n))]


def referencia():
    pe = pefile.PE(REF)
    base = pe.OPTIONAL_HEADER.ImageBase
    img = pe.get_memory_mapped_image()
    nombres = {}
    for d in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in d.imports:
            nombres[imp.address] = "%s!%s" % (d.dll.decode(), (imp.name or b"#%d" % imp.ordinal).decode())
    ref = Imagen(img, base)
    llamadas = []
    for m in re.finditer(rb"\xff\x15(....)", img, re.S):
        cas = struct.unpack("<I", m.group(1))[0]
        if cas in nombres:
            va = base + m.start()
            llamadas.append((va, nombres[cas], ref.antes(va), ref.despues(va + 6)))
    return llamadas


def puntaje(a, b, c, d):
    """Coincidencias exactas: antes alineado desde el final, después desde el principio."""
    return sum(x == y for x, y in zip(reversed(a), reversed(c))) + sum(x == y for x, y in zip(b, d))


def gemela(eda, va, llamadas, largo=6):
    """(API, puntaje, segunda) para el sitio va del exe (el `call` mide `largo` bytes)."""
    a, b = eda.antes(va), eda.despues(va + largo)
    mejores = {}
    for _, api, c, d in llamadas:
        p = puntaje(a, b, c, d)
        if p > mejores.get(api, -1):
            mejores[api] = p
    orden = sorted(mejores.items(), key=lambda x: -x[1])
    if not orden:
        return None, 0, 0
    segunda = orden[1][1] if len(orden) > 1 else 0
    return orden[0][0], orden[0][1], segunda


def aceptada(p, segunda):
    return p >= MINIMO and p - segunda >= VENTAJA


def exe():
    ruta = cp.exe_a_usar()
    img, base, secs = cp.imagen(ruta)
    pe = pefile.PE(ruta)
    nombres = {}
    for d in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in d.imports:
            nombres[imp.address] = (imp.name or b"").decode()
    return Imagen(img, base), img, base, secs, nombres


def trampas(img, base, secs):
    va, vsize = secs[0]
    out = []
    for a in range(va, va + vsize - 5):
        if img[a] == 0xE8:
            d = (base + a + 5 + struct.unpack_from("<i", img, a + 1)[0]) & 0xFFFFFFFF
            if d == cp.TRAMPA + (base + a - cp.BASE) and CRT[0] <= base + a < CRT[1]:
                out.append(base + a)
    return out


def corto(api):
    return api.split("!")[1] if api else api


# kernel32 REENVÍA estas a ntdll: son la misma función con dos nombres (el exe tiene la de ntdll)
REENVIADAS = {"HeapAlloc": "RtlAllocateHeap", "HeapReAlloc": "RtlReAllocateHeap", "HeapFree": "RtlFreeHeap",
              "HeapSize": "RtlSizeHeap", "EnterCriticalSection": "RtlEnterCriticalSection",
              "LeaveCriticalSection": "RtlLeaveCriticalSection",
              "DeleteCriticalSection": "RtlDeleteCriticalSection",
              "InitializeCriticalSection": "RtlInitializeCriticalSection",
              "TryEnterCriticalSection": "RtlTryEnterCriticalSection"}


def misma(a, b):
    a, b = corto(a) if "!" in a else a, corto(b) if "!" in b else b
    return a == b or REENVIADAS.get(a) == b or REENVIADAS.get(b) == a


def control():
    eda, img, base, secs, nombres = exe()
    llamadas = referencia()
    print("msvcr71.dll: %d llamadas a Windows con nombre" % len(llamadas))
    bien = mal = sin = 0
    errores = []
    for m in re.finditer(rb"\xff\x15(....)", img, re.S):
        va = base + m.start()
        cas = struct.unpack("<I", m.group(1))[0]
        if not (CRT[0] <= va < CRT[1]) or not nombres.get(cas):
            continue
        api, p, seg = gemela(eda, va, llamadas)
        if not aceptada(p, seg):
            sin += 1
        elif misma(api, nombres[cas]):
            bien += 1
        else:
            mal += 1
            errores.append("%08x  sabido %s · gemela %s (%d vs %d)" % (va, nombres[cas], api, p, seg))
    print("sitios de la CRT YA resueltos: %d acierta · %d se equivoca · %d no se anima" % (bien, mal, sin))
    for e in errores[:20]:
        print("  ⛔", e)
    # ★ el revés: código del JUEGO (fuera de la CRT) no tiene gemela en la CRT
    falsos = 0
    juego = [base + m.start() for m in re.finditer(rb"\xff\x15(....)", img, re.S)
             if 0x450000 <= base + m.start() < 0x600000][:200]
    for va in juego:
        api, p, seg = gemela(eda, va, llamadas)
        falsos += aceptada(p, seg)
    print("★ el revés: %d llamadas del juego (no son de la CRT) → %d con «gemela» aceptada" % (len(juego), falsos))
    return mal == 0 and bien > 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "control":
        return 0 if control() else 1
    eda, img, base, secs, _ = exe()
    llamadas = referencia()
    ts = trampas(img, base, secs)
    ok = 0
    for va in ts:
        api, p, seg = gemela(eda, va, llamadas)
        marca = "✅" if aceptada(p, seg) else "  "
        ok += aceptada(p, seg)
        print("%s %08x  %-40s %2d (2ª %2d)" % (marca, va, api, p, seg))
    print("→ %d de %d trampas de la CRT con gemela clara" % (ok, len(ts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
