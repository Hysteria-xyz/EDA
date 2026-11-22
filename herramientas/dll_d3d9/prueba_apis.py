r"""prueba_apis.py -- ★ (21-nov) que la lista de eda_apis.c (las llamadas sin resolver que la dll repara) sea SEGURA:

  · cada sitio de la lista está en documentacion/APIS_A_MANO.md con la MISMA API, de KERNEL32, y con la prueba más
    fuerte de esa tabla: la «gemela» en msvcr71.dll (la CRT de VC 7.1 que EDA trae adentro) con 17 o 18 de 18;
  · en exe/EDA_limpio.exe está, en cada uno, la trampa exacta (E8 → 0xD0000000 + sitio − 0x400000);
  · el sello y el tamaño del PE coinciden con los de eda_apis.c;
  · el revés: ningún sitio sin prueba fuerte, ni de otra dll, ni repetido.

    python herramientas/dll_d3d9/prueba_apis.py              (las pruebas)
    python herramientas/dll_d3d9/prueba_apis.py clasificar   (las ~112 llamadas sin resolver YA medidas, por riesgo)
"""
import hashlib
import os
import re
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
EXE = os.path.join(RAIZ, "exe", "EDA_limpio.exe")
TABLA = os.path.join(RAIZ, "documentacion", "APIS_A_MANO.md")
FUENTE = os.path.join(AQUI, "eda_apis.c")


def lista():
    t = open(FUENTE, encoding="utf-8").read()
    sitios = [(int(a, 16), b) for a, b in re.findall(r'\{0x([0-9A-Fa-f]+), "(\w+)"\}', t)]
    num = {k: int(v, 16) for k, v in re.findall(r"#define (API_EXE_\w+) 0x([0-9A-Fa-f]+)u", t)}
    return sitios, num


def tabla():
    filas = {}
    for linea in open(TABLA, encoding="utf-8"):
        m = re.match(r"\| 0x([0-9A-F]+) \| ([A-Za-z0-9]+\.dll)!(\w+) \| (.*)\|\s*$", linea)
        if m:
            filas.setdefault(int(m.group(1), 16), []).append((m.group(2).upper(), m.group(3), m.group(4)))
    return filas


def prueba(texto):
    m = re.search(r"\*\*(\d+) de 18\*\*", texto)
    if "GEMELA" in texto and m:
        return "gemela %s/18" % m.group(1), int(m.group(1))
    if "CORRIGE" in texto:
        return "corregida a mano", 0
    return "a mano (argumentos)", 0


class Exe:
    def __init__(self, ruta):
        self.d = open(ruta, "rb").read()
        d = self.d
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        self.sello = struct.unpack_from("<I", d, pe + 8)[0]
        self.tam = struct.unpack_from("<I", d, pe + 24 + 56)[0]
        n = struct.unpack_from("<H", d, pe + 6)[0]
        so = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
        self.secs = [struct.unpack_from("<8sIIII", d, so + 40 * i) for i in range(n)]

    def bytes_en(self, va, n):
        rva = va - 0x400000
        for _, vs, v, rs, ro in self.secs:
            if v <= rva < v + max(vs, rs):
                o = ro + rva - v
                return self.d[o:o + n]
        return b""

    def es_trampa(self, va):
        b = self.bytes_en(va, 5)
        return len(b) == 5 and b[0] == 0xE8 and (va + 5 + struct.unpack("<i", b[1:])[0]) & 0xFFFFFFFF == \
            0xD0000000 + va - 0x400000

    def trampas(self):
        """todos los `E8` del exe que van a la zona de trampas (sitio → sí)"""
        r = []
        d = self.d
        for _, vs, v, rs, ro in self.secs:
            for i in range(ro, ro + rs - 5):
                if d[i] == 0xE8:
                    va = 0x400000 + v + i - ro
                    if (va + 5 + struct.unpack_from("<i", d, i + 1)[0]) & 0xFFFFFFFF == 0xD0000000 + va - 0x400000:
                        r.append(va)
        return r


def zona(va):
    if va >= 0x7DD000:
        return "CRT de VC 7.1"
    if 0x7CE000 <= va < 0x7D8000:
        return "protección / actualizador / cripto"
    if 0x720000 <= va < 0x750000:
        return "motor: red e hilos"
    return "juego / motor"


def control():
    ok = []

    def chequear(t, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", t, d))
        ok.append(bool(c))
    sitios, num = lista()
    filas = tabla()
    exe = Exe(EXE)
    chequear("exe/EDA_limpio.exe es el 0799387e", hashlib.md5(exe.d).hexdigest().startswith("0799387e"))
    chequear("el sello y el tamaño del PE coinciden con eda_apis.c",
             exe.sello == num.get("API_EXE_SELLO") and exe.tam == num.get("API_EXE_TAMANO"),
             "%08X/%08X" % (exe.sello, exe.tam))
    chequear("la lista no repite sitios", len(set(s for s, _ in sitios)) == len(sitios))
    malos = []
    for s, fn in sitios:
        f = filas.get(s, [])
        if not f or len(set((a, b) for a, b, _ in f)) != 1:
            malos.append("0x%X sin fila única" % s)
            continue
        dll, api, texto = f[0]
        nombre, n = prueba(texto)
        if dll != "KERNEL32.DLL" or api != fn or n < 17:
            malos.append("0x%X: tabla %s!%s (%s), lista %s" % (s, dll, api, nombre, fn))
    chequear("cada sitio de la lista: misma API en APIS_A_MANO.md, de KERNEL32, con gemela 17-18/18", not malos, malos)
    chequear("en cada sitio de la lista está la trampa exacta en el exe", all(exe.es_trampa(s) for s, _ in sitios),
             [hex(s) for s, _ in sitios if not exe.es_trampa(s)])
    chequear("★ el sitio de la caída del 21-nov (0x7F4626, IsValidLocale) está en la lista",
             (0x7F4626, "IsValidLocale") in sitios)
    debiles = [s for s, f in filas.items() if exe.es_trampa(s) and prueba(f[0][2])[1] < 17]
    chequear("★ el revés: ninguno de los %d sitios con prueba más débil entró a la lista" % len(debiles),
             not set(debiles) & set(s for s, _ in sitios))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def clasificar():
    sitios, _ = lista()
    en_lista = set(s for s, _ in sitios)
    filas = tabla()
    exe = Exe(EXE)
    todas = exe.trampas()
    medidas = [s for s in todas if s in filas]
    print("Trampas en el exe: %d · con su API ya medida en APIS_A_MANO.md: %d · sin medir: %d\n"
          % (len(todas), len(medidas), len(todas) - len(medidas)))
    print("| sitio | API | prueba | zona | ¿en la lista? |")
    print("|---|---|---|---|---|")
    orden = {"CRT de VC 7.1": 0, "motor: red e hilos": 1, "juego / motor": 2, "protección / actualizador / cripto": 3}
    for s in sorted(medidas, key=lambda x: (orden[zona(x)], x)):
        dll, api, texto = filas[s][0]
        print("| 0x%X | %s!%s | %s | %s | %s |" % (s, dll.split(".")[0], api, prueba(texto)[0], zona(s),
                                                   "**sí**" if s in en_lista else "no"))
    return 0


if __name__ == "__main__":
    sys.exit(clasificar() if sys.argv[1:2] == ["clasificar"] else control())
