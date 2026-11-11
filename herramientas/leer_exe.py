r"""leer_exe -- leer el EDA.exe VOLCADO de memoria: textos, quién los usa, desensamblado, llamadores.

Adaptado de `R2B\herramientas\leer_exe.py` (proyecto R2Beat) el 2026-11-08. Lo que cambia:
el original lee un .exe de disco con pefile; acá el material es el VOLCADO de memoria
(`_trabajo/volcado/<corrida>/imagen.bin`), donde **archivo = memoria**: el offset dentro de
imagen.bin + 0x400000 ES la dirección virtual. Por eso no hace falta pefile para las conversiones.

    py herramientas\leer_exe.py textos GameGuard        # textos que contienen algo (con su VA)
    py herramientas\leer_exe.py usos 0x48b483           # quién referencia esa VA (push/mov/lea/call)
    py herramientas\leer_exe.py dis 0x403af0 0x60       # desensamblar desde una VA
    py herramientas\leer_exe.py llamadores 0x403af0     # quién llama a esa función (sigue los thunks)
    py herramientas\leer_exe.py func 0x403af0           # desensambla hasta el ret / probable fin
    py herramientas\leer_exe.py control                 # ★ comprueba que la herramienta ve bien

⚠ `dis` desarma LINEAL: si la VA no es el comienzo de una instrucción, las primeras líneas salen
  basura. Empezar en el inicio de la función.
⚠ El volcado es de un juego VIVO: las direcciones de las DLL (kernel32…) son las de ESA corrida.
  Las del propio EDA.exe (0x400000..) sí son estables: no tiene relocaciones activas.
"""
import glob
import os
import re
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

from capstone import CS_ARCH_X86, CS_MODE_32, Cs

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 0x400000
# las secciones del volcado (va_ini, va_fin, nombre) — medidas en MEDICIONES.md
SECCIONES = [(0x401000, 0x88A000, "cod1"), (0x88A000, 0x90C000, "cod2"),
             (0x90C000, 0x94D000, "datos"), (0x94D000, 0x94E000, ".rsrc"),
             (0x94E000, 0x981000, "s5"), (0x981000, 0x982000, "s6"),
             (0x982000, 0x9D5000, ".data-ASPR"), (0x9D5000, 0x9D7000, ".adata")]
EJECUTABLES = (0x401000, 0x90C000)        # dónde buscar código


def volcado_mas_nuevo():
    cs = sorted(glob.glob(os.path.join(RAIZ, "_trabajo", "volcado", "*", "imagen.bin")))
    if not cs:
        sys.exit("[!] no hay ningún _trabajo/volcado/*/imagen.bin — correr volcar_exe.py primero")
    return cs[-1]


class Img:
    def __init__(self, ruta=None):
        self.ruta = ruta or volcado_mas_nuevo()
        self.d = open(self.ruta, "rb").read()
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)

    def va2off(self, va):
        o = va - BASE
        return o if 0 <= o < len(self.d) else None

    def sec(self, va):
        return next((n for a, b, n in SECCIONES if a <= va < b), "?")

    # ---------- textos ----------
    def textos(self, patron, minimo=4):
        rx = re.compile(re.escape(patron).encode(), re.I)
        out = []
        for m in re.finditer(rb"[ -~]{%d,}" % minimo, self.d):
            if rx.search(m.group()):
                out.append((BASE + m.start(), m.group().decode("latin1")))
        for m in re.finditer(rb"(?:[ -~]\x00){%d,}" % minimo, self.d):
            s = m.group().decode("utf-16le")
            if rx.search(s.encode("latin1", "replace")):
                out.append((BASE + m.start(), "W:" + s))
        return out

    # ---------- quién usa una dirección ----------
    def usos(self, va, solo_codigo=False):
        """Busca la VA como valor de 4 bytes. Devuelve (dónde, sección, cómo).

        ⚠ En 5,8 MB, CUALQUIER secuencia de 4 bytes aparece por casualidad. Por eso cada hit se
        clasifica mirando el byte/opcode de antes: sólo `push imm32`, `mov reg,imm32`,
        `mov [..],imm32`, `cmp/add eax,imm32` y `lea`/`mov` con dirección absoluta cuentan como
        referencia de CÓDIGO. El resto queda como "dato" (puede ser una tabla de punteros… o azar).
        `solo_codigo=True` devuelve nada más las de código. El control del final usa esto."""
        aguja = struct.pack("<I", va)
        out, i = [], 0
        while (i := self.d.find(aguja, i)) >= 0:
            donde, como = BASE + i, "dato"
            p1, p2 = self.d[i - 1] if i else 0, self.d[i - 2] if i > 1 else 0
            if p1 == 0x68:
                como = "push"
            elif 0xB8 <= p1 <= 0xBF:
                como = "mov reg"
            elif p1 in (0xA1, 0xA3, 0x05, 0x3D, 0x2D, 0x25, 0xE9, 0xE8):
                como = "inmediato"
            elif p2 in (0xC7, 0x8D, 0x8B, 0x89, 0xFF, 0x81, 0x83):
                como = "modrm"
            if solo_codigo and como == "dato":
                i += 1
                continue
            out.append((donde, self.sec(donde), como))
            i += 1
        return out

    def dis(self, va, n=0x40):
        o = self.va2off(va)
        if o is None:
            return []
        return list(self.md.disasm(self.d[o:o + n], va))

    def func(self, va, tope=0x400):
        """Desensambla hasta el primer `ret` que no esté dentro de un salto hacia adelante."""
        salida, lejos = [], va
        for ins in self.md.disasm(self.d[self.va2off(va):self.va2off(va) + tope], va):
            salida.append(ins)
            if ins.mnemonic.startswith("j") and ins.op_str.startswith("0x"):
                try:
                    lejos = max(lejos, int(ins.op_str, 16))
                except ValueError:
                    pass
            if ins.mnemonic in ("ret", "retn") and ins.address >= lejos:
                break
        return salida

    def llamadores(self, va, profundidad=1):
        """call rel32 hacia `va`. Si el destino es un thunk (`jmp xxx`), sigue hacia atrás."""
        vistos, pendientes, out = set(), [(va, 0)], []
        while pendientes:
            obj, niv = pendientes.pop()
            if obj in vistos or niv > profundidad:
                continue
            vistos.add(obj)
            for ini, fin in [EJECUTABLES]:
                o, lim = self.va2off(ini), self.va2off(fin)
                i = o
                while i < lim - 5:
                    i = self.d.find(b"\xe8", i, lim)
                    if i < 0:
                        break
                    rel = struct.unpack_from("<i", self.d, i + 1)[0]
                    if BASE + i + 5 + rel == obj:
                        llamador = BASE + i
                        out.append((llamador, obj))
                        ins = self.dis(obj, 8)
                        if niv == 0 and ins and ins[0].mnemonic == "jmp":
                            pendientes.append((llamador, niv + 1))
                    i += 1
        return out


# ---------- ★ el control ----------
def control():
    """Comprueba que la herramienta ve bien, con casos de respuesta CONOCIDA y sus controles al revés."""
    g = Img()
    ok = True

    def chequear(nombre, cond, detalle=""):
        nonlocal ok
        print("  %s %s %s" % ("✅" if cond else "⛔", nombre, detalle))
        ok = ok and cond

    print("control sobre %s" % g.ruta)
    # 1) un texto que SABEMOS que está (medido el 08-nov) y uno que NO puede estar
    t = g.textos("LithTech build")
    chequear("encuentra un texto conocido", len(t) == 1, "(%d)" % len(t))
    chequear("NO inventa un texto ausente", not g.textos("EsteTextoNoExisteEnEda2009"))
    # 2) ese texto tiene que ser usado por alguien; y el esperado del control al revés se DERIVA
    #    de él: va+1 cae en medio del texto, así que nadie en el mundo lo referencia.
    if t:
        u = g.usos(t[0][0], solo_codigo=True)
        chequear("el texto conocido tiene usos de código", len(u) >= 1, "(%d)" % len(u))
        malo = g.usos(t[0][0] + 1, solo_codigo=True)
        chequear("NO inventa usos de una VA que nadie puede referenciar (texto+1)",
                 not malo, "(%d)" % len(malo))
        # y el uso encontrado tiene que desensamblar como push/mov de ESA dirección
        if u:
            ins = g.dis(u[0][0] - 1, 8)
            chequear("el uso desensambla como referencia real",
                     bool(ins) and ("%x" % t[0][0]) in ins[0].op_str,
                     "(%s %s)" % (ins[0].mnemonic, ins[0].op_str) if ins else "")
    # 4) desensamblar el comienzo de una función real da un prólogo
    pro = g.d.find(b"\x55\x8b\xec", g.va2off(0x401000))
    ins = g.dis(BASE + pro, 8)
    chequear("desensambla un prólogo", len(ins) >= 2 and ins[0].mnemonic == "push"
             and ins[1].mnemonic == "mov", "(%s / %s)" % (ins[0].mnemonic, ins[1].mnemonic) if ins else "")
    print("  →", "TODO BIEN" if ok else "ALGO FALLA")
    return 0 if ok else 1


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "control":
        return control()
    g = Img()
    cmd = sys.argv[1]
    if cmd == "textos":
        for va, s in g.textos(sys.argv[2]):
            print("%08x [%s] %s" % (va, g.sec(va), s[:160]))
    elif cmd == "usos":
        for va, sec, como in g.usos(int(sys.argv[2], 0)):
            print("%08x [%-10s] %s" % (va, sec, como))
    elif cmd in ("dis", "func"):
        va = int(sys.argv[2], 0)
        ins = g.func(va) if cmd == "func" else g.dis(va, int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x40)
        for i in ins:
            print("%08x  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    elif cmd == "llamadores":
        for q, a in g.llamadores(int(sys.argv[2], 0)):
            print("%08x -> %08x" % (q, a))
    else:
        sys.exit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
