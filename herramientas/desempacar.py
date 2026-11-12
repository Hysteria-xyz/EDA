r"""desempacar -- reconstruir un EDA.exe SIN ASProtect a partir del volcado de memoria.

El volcado (`volcar_exe.py`) ya trae el código desempacado, pero no CORRE: le falta (1) el punto de
entrada original del juego —ASProtect lo reemplaza por su cargador— y (2) una tabla de imports con
NOMBRES (el volcado tiene las direcciones de ESA corrida, que cambian en cada reinicio).
Esto arma las dos cosas y escribe un exe nuevo.

    py herramientas\desempacar.py iat          # qué casilleros de import hay y a qué función van
    py herramientas\desempacar.py oep          # dónde arranca el juego de verdad
    py herramientas\desempacar.py construir    # escribe _trabajo/volcado/<corrida>/EDA_libre.exe
    py herramientas\desempacar.py control      # ★ comprueba que la resolución de nombres no miente

⚠ El volcado se tomó con el juego VIVO: las direcciones de las DLL son las de esa corrida, por eso
  `modulos.json` (base y ruta de cada DLL) es imprescindible para traducirlas a nombres.
"""
import glob
import json
import re
import os
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

import pefile
from capstone import CS_ARCH_X86, CS_MODE_32, Cs

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 0x400000
# ★ la trampa para los sitios que todavía NO sabemos a qué API iban (10-nov). Su `call` se
#   redirige a BASE_TRAMPA + (sitio - 0x400000), que es memoria que no existe: el exe se cae ahí
#   y la DIRECCIÓN DEL CRASH dice exactamente qué sitio se alcanzó. Sin esto el `call` se iba a
#   la memoria de ASProtect y no se sabía cuál de los 228 había sido.
#   Así se averigua qué sitios están DE VERDAD en el camino del arranque, que son los únicos que
#   hay que resolver para que el juego abra.
BASE_TRAMPA = 0xD0000000
CODIGO = (0x401000, 0x90C000)        # las secciones ejecutables, en VA

# ⚠ Lo que la emulación contesta a veces pero NINGÚN compilador pone en una tabla de imports:
#   son las tripas de otra API (lo que hace `DeleteFileA` por dentro para pasar el nombre a
#   Unicode) o el camino de excepción del propio emulador, que no puede abrir una ventana.
#   Medido el 09-nov: 12 sitios "daban" RtlRaiseException y 6 Basep8Bit…, lo cual es imposible.
#   Un sitio así se cuenta como SIN RESOLVER: es mejor que inyectarle un import equivocado.
NUNCA_SE_IMPORTAN = {
    "RtlRaiseException", "RtlRaiseStatus", "RtlSetLastWin32Error", "RtlGetLastWin32Error",
    "MessageBoxTimeoutA", "MessageBoxTimeoutW", "RtlCustomCPToUnicodeN",
    "RtlMultiByteToUnicodeN", "RtlUnicodeToMultiByteN", "RtlUnicodeToCustomCPN",
    "RtlUnicodeToMultiByteSize", "RtlMultiByteToUnicodeSize", "RtlGetCurrentDirectory_U",
    "RtlInitAnsiStringEx", "RtlInitUnicodeStringEx", "RtlFreeUnicodeString",
    "memcpy", "memset", "memmove", "strlen", "wcslen",
}


# ★ (13-nov) FUNCIONES DE UNA SOLA INSTRUCCIÓN: el compilador hizo `jmp [API]` (la llamada de cola)
#   y ASProtect lo desvió igual que un `call`. Reponerlas como `call [x]` hace que la API vuelva a
#   +6, que es el COMIENZO DE OTRA FUNCIÓN. Cada una: un `ret` justo antes, la función siguiente a +6,
#   y la misma forma en `msvcr71.dll` (la CRT de VC 7.1).
SALTOS_A_MANO = {
    0x7F525A: "_getpid de la CRT = jmp [GetCurrentProcessId]; ret en 0x7F5259, la función siguiente "
              "arranca en 0x7F5260; la llama tmpnam (0x7E7CA6)",
    0x7E8F64: "__threadid = jmp [GetCurrentThreadId]; ret en 0x7E8F63, sigue __threadhandle",
    0x7E8F6A: "__threadhandle = jmp [GetCurrentThread]; la función siguiente arranca en 0x7E8F70",
}


def en_tabla_de_saltos(exe, sitio, desviados):
    """★ (13-nov, MEDICIONES §55) ¿El sitio está ADENTRO de una tabla de saltos del compilador
    (`jmp dword ptr [casillero]` = FF 25, uno cada 6 bytes)? Ahí lo que ASProtect desvió era un
    `jmp`, no un `call`: reponerlo como `call [x]` haría que la API vuelva a la tabla y siga con el
    salto de al lado. Se pide tabla a los DOS lados (saltando por encima de otros sitios desviados,
    que en el exe todavía son `E8`): un `call [x]` normal pegado a un único `jmp [y]` no cuenta."""
    def lado(paso):
        v = sitio + paso
        for _ in range(256):
            o = v - BASE
            if not (0 <= o <= len(exe) - 6):
                return False
            if exe[o] == 0xFF and exe[o + 1] == 0x25:
                return True
            if v in desviados and exe[o] == 0xE8:
                v += paso
                continue
            return False
        return False
    return lado(6) and lado(-6)


def corrida_mas_nueva():
    cs = sorted(glob.glob(os.path.join(RAIZ, "_trabajo", "volcado", "*", "imagen.bin")))
    if not cs:
        sys.exit("[!] no hay volcado — correr volcar_exe.py con el juego abierto")
    return os.path.dirname(cs[-1])


class Resolvedor:
    """dirección de la corrida  ->  («kernel32.dll», «GetStartupInfoA»).

    Cómo: con `modulos.json` se sabe en qué DLL cayó la dirección y en qué RVA; ese RVA se busca en
    la tabla de exports del ARCHIVO de esa DLL. Los exports reenviados (el `kernel32!X` que en
    realidad vive en `kernelbase`) se devuelven con el nombre de la DLL que uno querría importar."""

    PREFERIDAS = ("kernel32.dll", "user32.dll", "advapi32.dll", "ole32.dll", "oleaut32.dll",
                  "shell32.dll", "gdi32.dll", "ws2_32.dll", "winmm.dll", "msvcrt.dll")

    def __init__(self, mods):
        self.mods = [m for m in mods if m["nombre"].lower() != "eda.exe"]
        self.cache = {}
        self.exports = {}        # nombre dll -> {rva: nombre}
        self.por_nombre = {}     # nombre dll -> {nombre: rva}

    @staticmethod
    def ruta_real(m):
        """⚠ El juego es de 32 bits y sus DLL del sistema viven en SysWOW64, pero Python (64 bits)
        que lea «C:\\Windows\\System32\\user32.dll» abre la de 64 bits: los RVA no coinciden con
        nada y todo queda sin resolver (pasó el 08-nov). Se elige la copia cuyo SizeOfImage sea
        igual al tamaño que el módulo ocupa en memoria — comprobado, no supuesto."""
        candidatas = [m["ruta"]]
        baja = m["ruta"].lower()
        if "\\system32\\" in baja:
            i = baja.index("\\system32\\")
            candidatas.insert(0, m["ruta"][:i] + "\\SysWOW64\\" + m["ruta"][i + 10:])
        for r in candidatas:
            try:
                pe = pefile.PE(r, fast_load=True)
                coincide = pe.OPTIONAL_HEADER.SizeOfImage == m["tam"]
                pe.close()
                if coincide:
                    return r
            except Exception:                                # noqa: BLE001
                continue
        return None

    def _tabla(self, m):
        n = m["nombre"].lower()
        if n not in self.exports:
            rvas, nombres = {}, {}
            try:
                pe = pefile.PE(self.ruta_real(m), fast_load=True)
                pe.parse_data_directories(
                    directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
                for e in getattr(pe, "DIRECTORY_ENTRY_EXPORT", type("x", (), {"symbols": []})).symbols:
                    if e.name:
                        rvas[e.address] = e.name.decode()
                        nombres[e.name.decode()] = e.address
                pe.close()
            except Exception:                                # noqa: BLE001
                pass
            self.exports[n], self.por_nombre[n] = rvas, nombres
        return self.exports[n]

    def modulo(self, va):
        for m in self.mods:
            if m["base"] <= va < m["base"] + m["tam"]:
                return m
        return None

    def __call__(self, va):
        if va in self.cache:
            return self.cache[va]
        r = None
        m = self.modulo(va)
        if m:
            nombre = self._tabla(m).get(va - m["base"])
            if nombre:
                dll = m["nombre"]
                # si una DLL «clásica» exporta el mismo nombre, importarlo de ahí (más portable)
                for pref in self.PREFERIDAS:
                    mp = next((x for x in self.mods if x["nombre"].lower() == pref), None)
                    if mp and nombre in self.por_nombre.get(pref, self._tabla(mp) and
                                                            self.por_nombre[pref]):
                        dll = mp["nombre"]
                        break
                r = (dll, nombre)
        self.cache[va] = r
        return r


class Volcado:
    def __init__(self, carpeta=None):
        self.dir = carpeta or corrida_mas_nueva()
        self.img = bytearray(open(os.path.join(self.dir, "imagen.bin"), "rb").read())
        self.mods = json.load(open(os.path.join(self.dir, "modulos.json"), encoding="utf-8"))
        self.res = Resolvedor(self.mods)
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.disco = os.path.join(RAIZ, "cliente", "EDA.exe")

    def u32(self, va):
        o = va - BASE
        return struct.unpack_from("<I", self.img, o)[0] if 0 <= o < len(self.img) - 4 else 0

    # ---------- los casilleros de import ----------
    def slots(self):
        """Todo `call/jmp dword ptr [X]` del código cuyo X guarde un puntero a una DLL.
        Devuelve {X: (dll, función)} más la cuenta de los que no se pudieron resolver."""
        encontrados, sin_nombre = {}, {}
        o, lim = CODIGO[0] - BASE, CODIGO[1] - BASE
        i = o
        while i < lim - 6:
            b = self.img[i]
            x = None
            if b == 0xFF and self.img[i + 1] in (0x15, 0x25, 0x35):   # call/jmp/push dword [X]
                x = struct.unpack_from("<I", self.img, i + 2)[0]
            # ★ también `mov reg, dword ptr [X]` (8B 05/0D/15/1D/25/2D/35/3D) y `mov eax, [X]`
            #   (A1): el CRT hace `mov edi, [0x88A2A4]; call edi` (GetModuleHandleA). Sin esto esas
            #   casillas quedaban FUERA de la tabla de imports, con la dirección de la sesión de
            #   Windows en que se volcó: al reiniciar la PC el juego se caía al arrancar (11-nov)
            elif b == 0x8B and self.img[i + 1] in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
                x = struct.unpack_from("<I", self.img, i + 2)[0]
            elif b == 0xA1:
                x = struct.unpack_from("<I", self.img, i + 1)[0]
            if x is not None and BASE <= x < BASE + len(self.img) - 4:
                destino = self.u32(x)
                if self.res.modulo(destino):
                    n = self.res(destino)
                    (encontrados if n else sin_nombre)[x] = n or destino
            i += 1
        return encontrados, sin_nombre

    # ---------- mapa de funciones, sin depender de prólogos ----------
    def mapa(self):
        """{destino de call: [quiénes lo llaman]}. Los destinos de `call rel32` SON inicios de
        función: mucho más confiable que buscar `push ebp; mov ebp,esp` (medio CRT no lo tiene)."""
        if getattr(self, "_mapa", None):
            return self._mapa
        m = {}
        o, lim = CODIGO[0] - BASE, CODIGO[1] - BASE
        i = o
        while (i := self.img.find(b"\xe8", i, lim)) >= 0:
            t = BASE + i + 5 + struct.unpack_from("<i", self.img, i + 1)[0]
            if CODIGO[0] <= t < CODIGO[1]:
                m.setdefault(t, []).append(BASE + i)
            i += 1
        self._mapa = m
        self._inicios = sorted(m)
        return m

    def funcion_de(self, va):
        """La función que contiene `va`: el inicio de función conocido más cercano por debajo."""
        import bisect
        self.mapa()
        i = bisect.bisect_right(self._inicios, va) - 1
        return self._inicios[i] if i >= 0 else None

    def usuarios_de_slot(self, x):
        out = []
        for op in (b"\xff\x15", b"\xff\x25"):
            ag = op + struct.pack("<I", x)
            i = CODIGO[0] - BASE
            while (i := self.img.find(ag, i, CODIGO[1] - BASE)) >= 0:
                out.append(BASE + i)
                i += 1
        return out

    # ---------- el arranque original ----------
    def oep_por_crt(self):
        """El arranque del CRT de Microsoft, deducido de su estructura:
        `__tmainCRTStartup` es la función que llama TANTO a la que crea el heap (HeapCreate)
        COMO a la que inicializa los hilos (FlsAlloc). Y el verdadero punto de entrada es su
        último ancestro: una función a la que **nadie llama** (nadie llama al entry point).
        Devuelve (va, explicación)."""
        s, _ = self.slots()
        porn = {fn: x for x, (d, fn) in s.items()}
        self.mapa()
        padres = {}
        for fn in ("HeapCreate", "FlsAlloc", "GetVersionExA", "GetStringTypeW", "LCMapStringW"):
            if fn not in porn:
                continue
            for u in self.usuarios_de_slot(porn[fn]):
                f = self.funcion_de(u)
                for ll in self._mapa.get(f, []):
                    p = self.funcion_de(ll)
                    if p:
                        padres.setdefault(p, set()).add(fn)
        cands = sorted(padres.items(), key=lambda kv: -len(kv[1]))
        if not cands or len(cands[0][1]) < 2:
            return None, "no hay una función que inicialice heap + hilos"
        start, que = cands[0]
        # subir mientras tenga un único llamador: el entry point no lo llama nadie
        cadena = [start]
        actual = start
        for _ in range(4):
            lls = {self.funcion_de(x) for x in self._mapa.get(actual, [])}
            lls.discard(None)
            if len(lls) != 1:
                break
            actual = lls.pop()
            cadena.append(actual)
        sin_llamadores = not self._mapa.get(actual)
        return actual, "inicializa %s; cadena %s; %s" % (
            "+".join(sorted(que)), " <- ".join(hex(c) for c in cadena),
            "nadie lo llama (= entry point)" if sin_llamadores else "⚠ todavía tiene llamadores")

    def oep(self):
        """El arranque del CRT de Microsoft: la función que usa GetStartupInfo + GetCommandLine +
        GetModuleHandle. Se la busca por los casilleros de esas APIs y de ahí se retrocede al
        prólogo. Devuelve (va, por_qué) o (None, motivo)."""
        slots, _ = self.slots()
        quiero = {"GetStartupInfoA": None, "GetStartupInfoW": None, "GetCommandLineA": None,
                  "GetCommandLineW": None, "GetModuleHandleA": None, "GetModuleHandleW": None}
        for x, (dll, fn) in slots.items():
            if fn in quiero and quiero[fn] is None:
                quiero[fn] = x
        usados = {fn: x for fn, x in quiero.items() if x}
        # dónde se usa cada uno
        usos = {}
        for fn, x in usados.items():
            aguja = b"\xff\x15" + struct.pack("<I", x)
            i = CODIGO[0] - BASE
            while (i := self.img.find(aguja, i, CODIGO[1] - BASE)) >= 0:
                usos.setdefault(BASE + i, set()).add(fn)
                i += 1
        # ★ y también por los sitios DESVIADOS ya resueltos (11-nov). Esto hacía falta: en EDA
        #   ASProtect desvió TODAS las llamadas del arranque del CRT, así que esas APIs no tienen
        #   casillero y el control «encuentra el arranque del juego» fallaba desde el principio.
        #   Ahora que sabemos a qué API va cada sitio, se usan también para ubicar el arranque —
        #   y así el control vuelve a decir algo: confirma, por otro camino, el OEP de la corrida 4.
        for sitio, (dll, fn) in self.desviados().items():
            if fn in quiero:
                usos.setdefault(sitio, set()).add(fn)
        if not usos:
            return None, "no encontré ni casilleros ni sitios resueltos del CRT"
        # el arranque del CRT: la zona donde conviven GetStartupInfo y GetCommandLine
        candidatos = []
        for va, fns in usos.items():
            cerca = set()
            for va2, f2 in usos.items():
                if abs(va2 - va) < 0x200:
                    cerca |= f2
            if any(f.startswith("GetStartupInfo") for f in cerca) and \
               any(f.startswith("GetCommandLine") for f in cerca):
                candidatos.append((va, cerca))
        if not candidatos:
            return None, "no hay ninguna función que use GetStartupInfo y GetCommandLine juntas"
        va = min(c[0] for c in candidatos)
        return self.inicio_de_funcion(va), "usa %s" % ", ".join(sorted(candidatos[0][1]))

    def inicio_de_funcion(self, va, atras=0x400):
        """Retrocede hasta el prólogo (`push ebp; mov ebp,esp`) precedido de relleno o de un ret."""
        o = va - BASE
        mejor = None
        for p in range(o - atras, o):
            if p < 0:
                continue
            if self.img[p:p + 3] == b"\x55\x8b\xec":
                ant = self.img[p - 1] if p else 0
                if ant in (0xCC, 0xC3, 0x90) or ant == 0:
                    mejor = BASE + p
        return mejor


    # ---------- las APIs que ASProtect emula ----------
    def regiones(self):
        """Las zonas ejecutables de ASProtect que volcó `volcar_exe.py` (sus stubs)."""
        if getattr(self, "_regs", None) is None:
            self._regs = {int(os.path.basename(f)[:-4], 16): open(f, "rb").read()
                          for f in glob.glob(os.path.join(self.dir, "regiones", "*.bin"))}
        return self._regs

    def region_de(self, va):
        for rb, b in self.regiones().items():
            if rb <= va < rb + len(b):
                return rb, b
        return None

    def export_cercano(self, va, tope=96):
        """(dll, función, cuántos bytes después del comienzo). Sirve porque los stubs devuelven el
        control a la API real UNOS POCOS bytes después de su comienzo."""
        import bisect
        m = self.res.modulo(va)
        if not m:
            return None
        t = self.res._tabla(m)
        rs = sorted(t)
        i = bisect.bisect_right(rs, va - m["base"]) - 1
        if i < 0:
            return None
        d = (va - m["base"]) - rs[i]
        return (m["nombre"], t[rs[i]], d) if d <= tope else None

    def api_de_stub(self, stub):
        """Qué API emula un stub de ASProtect.

        Cómo (medido el 08-nov): el stub hace `inc dword ptr [esp]` —saltea el byte sobrante del
        `call dword ptr [IAT]` original, que medía 6 y fue reemplazado por uno de 5— y salta a otra
        zona donde ASProtect copió **los primeros bytes de la API real**; al terminar esa copia
        devuelve el control a la API con `push <dirección dentro de la API>; ret`. Ese `push` es lo
        que delata cuál es: se busca el export que empieza unos pocos bytes antes."""
        r = self.region_de(stub)
        if not r:
            return None
        rb, b = r
        destino = None
        for i in self.md.disasm(bytes(b[stub - rb:stub - rb + 0x20]), stub):
            if i.mnemonic == "jmp" and i.op_str.startswith("0x") \
                    and not (rb <= int(i.op_str, 16) < rb + len(b)):
                destino = int(i.op_str, 16)
                break
        if destino is None:
            return None
        r2 = self.region_de(destino)
        if not r2:
            return None
        rb2, b2 = r2
        o = destino - rb2
        for m in re.finditer(rb"\x68(....)\xc3", bytes(b2[o:o + 0x200])):
            c = self.export_cercano(struct.unpack("<I", m.group(1))[0])
            if c:
                return c
        return None

    # ---------- escribir el exe nuevo ----------
    def desviados(self, ruta=None):
        """{sitio: (dll, función)} de los `call` que ASProtect desvió, medidos por
        `emular_stub.py todos`. Es el archivo que escribe esa herramienta."""
        # ★ Se prefiere la lista FINAL (`juntar_apis.py`: junta la emulación cruzada entre dos
        #   volcados con la lectura del stub, y descarta lo que choca entre métodos). Después la
        #   cruzada sola, y la corrida suelta como último respaldo.
        if not ruta:
            for n in ("apis_finales.json", "apis_cruzadas.json", "apis_emuladas.json"):
                c = os.path.join(RAIZ, "_trabajo", n)
                if os.path.exists(c):
                    ruta = c
                    break
        if not ruta or not os.path.exists(ruta):
            return {}
        self.fuente = os.path.basename(ruta)
        d, tirados = {}, {}
        for k, v in json.load(open(ruta, encoding="utf-8")).items():
            dll, _, fn = v.partition("!")
            if not (dll and fn):
                continue
            if fn in NUNCA_SE_IMPORTAN or fn.startswith("Basep"):
                tirados[int(k, 16)] = v
                continue
            d[int(k, 16)] = (dll.lower(), fn)
        self.tirados = tirados
        # ⛔⛔ ACÁ HABÍA UN RESPALDO Y HACÍA DAÑO (medido el 10-nov). Para los sitios que
        #   `juntar_apis.py` había DESCARTADO —los que chocan entre métodos— se usaba igual lo
        #   que decía `api_de_stub`, sin control. En 0x7D75AD eso puso `CryptReleaseContext`
        #   (2 argumentos) donde iba `CryptAcquireContextA` (5): la API limpió 8 bytes de pila
        #   en vez de 20, el `ret` se llevó como dirección de vuelta uno de los argumentos que
        #   sobraban (0xF0000000, que es CRYPT_VERIFYCONTEXT) y el exe se murió saltando ahí.
        #   ★ La lección: una respuesta EQUIVOCADA es peor que ninguna. Sin respuesta el `call`
        #   va a la trampa y el crash dice qué sitio falta; con una equivocada el exe se cae en
        #   otro lado y no se entiende por qué. El respaldo sigue disponible a mano
        #   (`py herramientas\desempacar.py stub <VA>`) pero no entra solo al exe.
        # ★★ EL CONTROL QUE FALTABA (11-nov): la función que declaramos tiene que SER un export de
        #    la DLL de la que la declaramos. Si no, Windows no carga el exe y lo único que dice es
        #    `C0000139 STATUS_ENTRYPOINT_NOT_FOUND` — sin nombre, sin dirección, nada.
        #    Pasó con `ADVAPI32.dll!CryptVerifySignature`: no existe, se llama
        #    `CryptVerifySignatureA` (las Crypt que llevan cadena tienen A y W). El nombre sólo se
        #    descubrió leyendo la pila del crash, que tenía la cadena en UTF-16.
        #    Si la variante `A` sí existe y la pelada no, se corrige; si no existe ninguna, se tira.
        self.inventadas, self.con_a = {}, {}
        for sitio in list(d):
            dll, fn = d[sitio]
            tabla = self.res.por_nombre.get(dll)
            if tabla is None:
                m = next((x for x in self.res.mods if x["nombre"].lower() == dll), None)
                if m:
                    self.res._tabla(m)                      # noqa: SLF001
                tabla = self.res.por_nombre.get(dll) or {}
            if fn in tabla:
                continue
            if fn + "A" in tabla:
                d[sitio] = (dll, fn + "A")
                self.con_a[sitio] = "%s!%s" % (dll, fn + "A")
            else:
                self.inventadas[sitio] = "%s!%s" % (dll, fn)
                del d[sitio]
        if self.inventadas:
            print("  ⛔ %d sitios con una función que NO es export de esa DLL: %s"
                  % (len(self.inventadas),
                     ", ".join("%08x %s" % (k, v) for k, v in list(self.inventadas.items())[:4])))
        if self.con_a:
            print("  ⚠ %d corregidas a la variante «A»: %s"
                  % (len(self.con_a), ", ".join(sorted(self.con_a.values())[:4])))
        self.por_lectura = {}
        return d

    def datos_iniciales(self, carpeta=None):
        """★★ Las páginas de DATOS como estaban ANTES de que arrancara el juego (10-nov).

        El exe se arma con el CÓDIGO de un volcado tardío —a los 25 s, cuando ASProtect ya
        descifró todo— pero ese volcado trae las globales con los valores de ESA corrida. Las
        escribe `volcar_todo.py --valores-iniciales`, que suspende el proceso y lo avanza de a
        2 ms hasta el último instante en que el CRT todavía no arrancó.
        ⇒ **código del tardío + datos del inicial**.

        Devuelve {dirección de página: 4096 bytes}, o {} si no está hecho (y entonces se usa el
        camino viejo: poner en cero lo que marcó `limpiar_datos.py`)."""
        carpeta = carpeta or os.path.join(RAIZ, "_trabajo", "datos_iniciales")
        ind = os.path.join(carpeta, "indice.txt")
        if not os.path.exists(ind):
            return {}
        blob = open(os.path.join(carpeta, "paginas.bin"), "rb").read()
        out = {}
        for l in open(ind):
            a, n, off = (int(x, 16) for x in l.split())
            out[a] = blob[off:off + n]
        return out

    def lector_temprano(self, carpeta=None):
        """El volcado TEMPRANO entero (`volcar_todo.py --temprano`), como respaldo de
        `datos_iniciales`: devuelve una función leer(va, n) o None."""
        carpeta = carpeta or os.path.join(RAIZ, "_trabajo", "volcado", "eda_temprano")
        ind = os.path.join(carpeta, "indice.txt")
        if not os.path.exists(ind):
            return None
        regiones = []
        for l in open(ind):
            a, b, c, t = l.split()
            regiones.append((int(a, 16), int(b, 16), int(c, 16)))
        regiones.sort()
        blob = open(os.path.join(carpeta, "todo.bin"), "rb").read()

        def leer(va, n):
            for rb, sz, off in regiones:
                if rb <= va and va + n <= rb + sz:
                    return blob[off + (va - rb):off + (va - rb) + n]
            return None

        return leer

    def secciones_del_disco(self):
        """[(nombre, va, tamaño redondeado a página)] leídas del EDA.exe original."""
        d = open(os.path.join(RAIZ, "cliente", "EDA.exe"), "rb").read()
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        n = struct.unpack_from("<H", d, pe + 6)[0]
        t = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
        out = []
        for i in range(n):
            nom, vsz, va = struct.unpack_from("<8sII", d, t + i * 40)
            out.append((nom.rstrip(b"\0").decode(errors="replace") or "(sin nombre)",
                        BASE + va, (vsz + 0xFFF) & ~0xFFF))
        return out

    def codigo_robado(self):
        """{dirección: bytes} del código que ASProtect se robó y hay que reponer, leído de
        `documentacion/CODIGO_ROBADO.md`. Cada fila trae su prueba escrita al lado; una fila que
        no se entienda o que no la traiga NO entra (ver ese archivo)."""
        ruta = os.path.join(RAIZ, "documentacion", "CODIGO_ROBADO.md")
        if not os.path.exists(ruta):
            return {}
        fila = re.compile(r"^\|\s*0x([0-9A-Fa-f]{6,8})\s*\|\s*((?:[0-9A-Fa-f]{2}\s+)*"
                          r"[0-9A-Fa-f]{2})\s*\|\s*([^|]+?)\s*\|\s*(\S[^|]*?)\s*\|\s*$")
        d, malas = {}, 0
        for l in open(ruta, encoding="utf-8"):
            if not l.startswith("|") or l.startswith("|---") or l.startswith("| dónde"):
                continue
            m = fila.match(l.rstrip("\n"))
            if not m or len(m.group(4)) < 40:
                malas += 1
                continue
            d[int(m.group(1), 16)] = bytes.fromhex(m.group(2))
        if malas:
            print("  ⚠ %d filas de CODIGO_ROBADO.md no se entienden o no traen prueba" % malas)
        return d

    def datos_de_corrida(self):
        """Las direcciones cuyo dword hay que poner en cero porque era estado de la corrida que
        volcamos, no un valor del archivo. Las mide `limpiar_datos.py` comparando dos volcados
        de dos corridas. Si el archivo no está, no se limpia nada (y el exe muere en 0x45BF6B)."""
        ruta = os.path.join(RAIZ, "_trabajo", "datos_de_corrida.txt")
        if not os.path.exists(ruta):
            print("  ⚠ falta %s — corré antes: py herramientas\\limpiar_datos.py" % ruta)
            return []
        return [int(l, 16) for l in open(ruta) if l.strip()]

    def sitios_desviados(self):
        """Los `call` que ASProtect desvió, leídos de `_trabajo/sitios_desviados.txt`.

        ⛔ NO se barre acá. Un barrido LINEAL de `0xE8` se desincroniza y da miles de sitios
           fantasma: lo hice el 09-nov y dio **14.295** donde hay **310** — y peor, llegó a
           escribir el parche encima de código que no era una llamada. La lista buena la hace
           `emular_stub.py sitios`, con un barrido RECURSIVO desde los inicios de función."""
        ruta = os.path.join(RAIZ, "_trabajo", "sitios_desviados.txt")
        if not os.path.exists(ruta):
            print("[!] falta %s — correr `emular_stub.py sitios`" % ruta)
            return []
        return [int(l, 16) for l in open(ruta) if l.strip()]

    def construir(self, salida=None, oep=None, desviados=None):
        """Arma un exe con el código desempacado, el arranque original y una tabla de imports
        por NOMBRE. Devuelve (ruta, informe).

        ★ `desviados` ({sitio: (dll, fn)}) son las llamadas que ASProtect reemplazó por una suya.
        Se arreglan RESTAURANDO LA INSTRUCCIÓN ORIGINAL en su lugar, sin agregar nada: el `call
        dword ptr [casillero]` medía 6 bytes (FF 15 + dirección) y el `call <stub>` que lo
        reemplazó mide 5 + 1 de relleno — el mismo espacio. Por eso el stub hace
        `inc dword ptr [esp]`: para saltear ese byte al volver. Así que los 6 bytes se reescriben
        tal cual eran y el juego vuelve a llamar a Windows directo."""
        img = bytearray(self.img)
        disco = open(self.disco, "rb").read()
        pe = struct.unpack_from("<I", disco, 0x3C)[0]
        nsec = struct.unpack_from("<H", disco, pe + 6)[0]
        opt = pe + 24
        tsec = opt + struct.unpack_from("<H", disco, pe + 20)[0]
        secs = [list(struct.unpack_from("<8sIIII", disco, tsec + i * 40)) for i in range(nsec)]
        hdr_tam = secs[0][2]                       # VirtualAddress de la 1ª sección

        # 1) los casilleros, agrupados en tiras contiguas de la misma DLL
        slots, _ = self.slots()
        tiras, orden = [], sorted(slots)
        for x in orden:
            dll, fn = slots[x]
            if tiras and tiras[-1][0] == dll and x == tiras[-1][2][-1] + 4:
                tiras[-1][2].append(x)
                tiras[-1][3].append(fn)
            else:
                tiras.append([dll, x, [x], [fn]])

        # 2) la sección nueva con la tabla de imports
        va_nueva = (BASE + len(img) + 0xFFF) & ~0xFFF
        rva = va_nueva - BASE
        descr = bytearray()
        resto = bytearray()
        nombres_dll = {}

        def meter(b, alin=2):
            while len(resto) % alin:
                resto.append(0)
            o = len(resto)
            resto.extend(b)
            while len(resto) % 2:
                resto.append(0)
            return o

        # ★ las llamadas desviadas: las que ya tienen casillero lo reusan; para las demás se
        #   agregan tiras nuevas, una por DLL. (Las tiras van antes de reservar los descriptores
        #   porque su cantidad decide cuántos descriptores hay.)
        desviados = desviados if desviados is not None else self.desviados()
        ya = {}
        for x, (dll, fn) in slots.items():
            ya.setdefault((dll.lower(), fn), x)
        parches, faltan = {}, {}
        for sitio, (dll, fn) in sorted(desviados.items()):
            if CODIGO[0] <= sitio < CODIGO[1] - 6:
                if (dll.lower(), fn) in ya:
                    parches[sitio] = ya[(dll.lower(), fn)]
                else:
                    faltan.setdefault(dll, []).append(fn)
        nuevas = [[dll, None, [], sorted(set(fns))] for dll, fns in sorted(faltan.items())]
        # reservamos el tamaño de los descriptores: 20 bytes cada uno + el nulo
        base_resto = 20 * (len(tiras) + len(nuevas) + 1)
        for dll, prim, xs, fns in tiras:
            if dll.lower() not in nombres_dll:
                nombres_dll[dll.lower()] = meter(dll.encode() + b"\0")
            oft = []
            for fn in fns:
                oft.append(rva + base_resto + meter(struct.pack("<H", 0) + fn.encode() + b"\0"))
            oft_off = meter(struct.pack("<%dI" % (len(oft) + 1), *oft, 0))
            descr.extend(struct.pack("<IIIII", rva + base_resto + oft_off, 0, 0,
                                     rva + base_resto + nombres_dll[dll.lower()], prim - BASE))
        # ★ las tiras NUEVAS (las de las llamadas desviadas): sus casilleros van en esta misma
        #   sección, en cero — los rellena Windows al cargar, igual que los otros.
        for t in nuevas:
            dll, _, _, fns = t
            if dll.lower() not in nombres_dll:
                nombres_dll[dll.lower()] = meter(dll.encode() + b"\0")
            oft = [rva + base_resto + meter(struct.pack("<H", 0) + fn.encode() + b"\0")
                   for fn in fns]
            oft_off = meter(struct.pack("<%dI" % (len(oft) + 1), *oft, 0), alin=4)
            # ⚠⚠ LOS CASILLEROS NO PUEDEN ARRANCAR EN CERO. El cargador de Windows recorre esta
            #    tabla hasta encontrar un cero, y lo toma como el FIN de la lista: si el primero
            #    es cero, decide que esa DLL no importa nada y NO ESCRIBE NADA. Medido el 09-nov:
            #    las 6 tiras nuevas quedaban en cero y el juego saltaba a la dirección 0, mientras
            #    las 64 viejas sí se rellenaban (traían las direcciones del volcado, no cero).
            #    ⇒ se arranca con el mismo puntero al nombre que la otra tabla, que es lo que
            #      pone cualquier compilador; el cargador después lo reemplaza por la dirección.
            slots_off = meter(struct.pack("<%dI" % (len(oft) + 1), *oft, 0), alin=4)
            t[1] = BASE + rva + base_resto + slots_off
            descr.extend(struct.pack("<IIIII", rva + base_resto + oft_off, 0, 0,
                                     rva + base_resto + nombres_dll[dll.lower()],
                                     rva + base_resto + slots_off))
        nuevo_slot, rangos = {}, []
        for dll, prim, _, fns in nuevas:
            rangos.append((prim, prim + 4 * len(fns)))
            for i, fn in enumerate(fns):
                nuevo_slot[(dll.lower(), fn)] = prim + 4 * i
        for sitio, (dll, fn) in sorted(desviados.items()):
            if sitio not in parches and CODIGO[0] <= sitio < CODIGO[1] - 6 \
                    and (dll.lower(), fn) in nuevo_slot:
                parches[sitio] = nuevo_slot[(dll.lower(), fn)]
        # ★★ EL CONTROL QUE FALTABA: todo casillero al que apunte un parche tiene que estar
        #    DENTRO de una tira declarada en la tabla de imports (si no, Windows no lo rellena y
        #    el juego salta a la dirección 0 — medido el 09-nov en 0x7E8F88), o ser uno de los
        #    casilleros que ya traía la imagen.
        viejos = set(slots)
        malos = [(s, x) for s, x in parches.items()
                 if x not in viejos and not any(a <= x < b for a, b in rangos)]
        assert not malos, "casilleros fuera de toda tira: %s" % (
            ", ".join("%08x->%08x" % m for m in malos[:5]))
        descr.extend(b"\0" * 20)
        idata = bytes(descr) + bytes(resto)
        tam_idata = (len(idata) + 0xFFF) & ~0xFFF

        # 3) la cabecera: raw = virtual, todo RWX, sin ASLR, entrada = el arranque real
        exe = bytearray(disco[:hdr_tam].ljust(hdr_tam, b"\0")) + img[hdr_tam:]
        # ⚠ la imagen termina en 0x…c00: sin este relleno la tabla queda 0x400 bytes corrida
        #    respecto del RVA que declara la cabecera, y el exe no carga (pasó el 08-nov).
        exe.extend(b"\0" * (rva - len(exe)))
        assert len(exe) == rva, "la sección nueva no quedó donde dice la cabecera"
        exe.extend(idata.ljust(tam_idata, b"\0"))
        for i, (nm, vs, va, rs, ro) in enumerate(secs):
            o = tsec + i * 40
            struct.pack_into("<III", exe, o + 8, vs, va, max(vs, 0))
            struct.pack_into("<I", exe, o + 20, va)                       # PointerToRawData = VA
            struct.pack_into("<I", exe, o + 36, 0xE0000040)               # RWX + datos
        struct.pack_into("<8sIIII", exe, tsec + nsec * 40, b".edaimp", len(idata), rva,
                         tam_idata, rva)
        struct.pack_into("<I", exe, tsec + nsec * 40 + 36, 0xC0000040)
        struct.pack_into("<H", exe, pe + 6, nsec + 1)                     # NumberOfSections
        struct.pack_into("<I", exe, opt + 16, (oep or 0x7E3A11) - BASE)   # AddressOfEntryPoint
        struct.pack_into("<I", exe, opt + 32, 0x1000)                     # SectionAlignment
        struct.pack_into("<I", exe, opt + 36, 0x1000)                     # FileAlignment
        struct.pack_into("<I", exe, opt + 56, rva + tam_idata)            # SizeOfImage
        dll_car = struct.unpack_from("<H", exe, opt + 70)[0]
        struct.pack_into("<H", exe, opt + 70, dll_car & ~0x0040)          # sin ASLR: hay VA fijas
        # No hay tabla de reubicaciones: el cargador debe respetar la base preferida
        #   (IMAGE_FILE_RELOCS_STRIPPED; aporte de Urek-Mazinoo, PR #1 del repo público).
        caracteristicas = struct.unpack_from("<H", exe, pe + 22)[0]
        struct.pack_into("<H", exe, pe + 22, caracteristicas | 0x0001)
        dirs = opt + 96
        for n in (1, 5, 9, 11, 12, 13):          # import, reloc, tls, bound, iat, delay
            struct.pack_into("<II", exe, dirs + n * 8, 0, 0)
        struct.pack_into("<II", exe, dirs + 1 * 8, rva, len(descr))
        # ★ y acá se deshace el desvío: los 6 bytes del `call <stub>` vuelven a ser el
        #   `call dword ptr [casillero]` que el compilador había puesto.
        puestos, no_eran, saltos = 0, 0, 0
        todos = set(parches) | set(self.sitios_desviados())
        en_tabla = {s for s in parches if en_tabla_de_saltos(exe, s, todos)}   # (antes de reescribir)
        en_tabla |= set(SALTOS_A_MANO) & set(parches)
        for sitio, slot in sorted(parches.items()):
            o = sitio - BASE
            if exe[o] == 0xE8:                      # control: tiene que haber un `call rel32` ahí
                # ★ (13-nov, MEDICIONES §55) en una TABLA DE SALTOS el original era `jmp [x]` (FF 25)
                struct.pack_into("<BBI", exe, o, 0xFF, 0x25 if sitio in en_tabla else 0x15, slot)
                puestos += 1
                saltos += sitio in en_tabla
            else:
                no_eran += 1
        # ★ y los que no sabemos: se les cambia el destino a la trampa (ver BASE_TRAMPA) para
        #   que, si el juego llega a uno, el crash diga CUÁL fue.
        trampas = 0
        for sitio in sorted(set(self.sitios_desviados()) - set(parches)):
            o = sitio - BASE
            if not (0 <= o <= len(exe) - 5) or exe[o] != 0xE8:
                continue
            destino = BASE_TRAMPA + (sitio - BASE)
            struct.pack_into("<I", exe, o + 1, (destino - (sitio + 5)) & 0xFFFFFFFF)
            trampas += 1
        # ★ y se repone el código que ASProtect se robó (ver `documentacion/CODIGO_ROBADO.md`).
        #   Va DESPUÉS de restaurar los `call`, porque esos bytes están justo pegados al sitio.
        repuestos = 0
        for d, bs in sorted(self.codigo_robado().items()):
            o = d - BASE
            assert 0 <= o <= len(exe) - len(bs), "código robado fuera del exe: %08x" % d
            exe[o:o + len(bs)] = bs
            repuestos += len(bs)

        # ★★ Y LOS DATOS, que es la otra mitad del problema. El exe sale de un volcado TARDÍO
        #   (a los 25 s, cuando ASProtect ya descifró todo el código), así que sus globales traen
        #   los valores de ESA corrida: punteros al heap, handles, ids de hilo, el índice de TLS.
        #   El juego los ve distintos de cero, cree que el objeto ya existe y explota (así moría
        #   en `0x45BF6B`).
        #   ⇒ Las páginas de datos se reemplazan por las del instante INICIAL
        #     (`volcar_todo.py --valores-iniciales`: el proceso suspendido y avanzado de a 2 ms
        #     hasta el último momento en que el CRT todavía no arrancó).
        #   ⚠ Y por qué páginas enteras y no sólo los dwords que marca `limpiar_datos.py`: ese
        #     método compara dos volcados tardíos, y **no ve un valor de corrida que salga igual
        #     en las dos corridas**. `0x92BE30` (`__tlsindex`) valía 7 las dos veces y quedaba sin
        #     marcar, con lo cual el exe arrancaba con un índice de TLS ya asignado.
        #   Si no está hecho el inicial, se cae al camino viejo: esos dwords en cero.
        paginas = self.datos_iniciales()
        del_inicial, borrados, fuera = 0, 0, 0
        for va, d in sorted(paginas.items()):
            o = va - BASE
            assert 0 <= o <= len(exe) - len(d), "página de datos fuera del exe: %08x" % va
            exe[o:o + len(d)] = d
            del_inicial += 1
        if not paginas:
            pronto = self.lector_temprano()
            for d in self.datos_de_corrida():
                o = d - BASE
                if not (0 <= o <= len(exe) - 4):
                    fuera += 1
                    continue
                v = pronto(d, 4) if pronto else None
                if v and len(v) == 4:
                    exe[o:o + 4] = v
                else:
                    struct.pack_into("<I", exe, o, 0)
                borrados += 1
            assert not fuera, "%d direcciones a limpiar caen fuera del exe" % fuera

        ruta = salida or os.path.join(self.dir, "EDA_libre.exe")
        open(ruta, "wb").write(exe)
        return ruta, {"tiras": len(tiras), "apis": len(slots),
                      "datos_de_corrida_en_cero": borrados, "con_trampa": trampas,
                      "paginas_de_datos_iniciales": del_inicial,
                      "bytes_robados_repuestos": repuestos,
                      "dlls": sorted({d for d, _, _, _ in tiras}), "oep": oep or 0x7E3A11,
                      "tam": len(exe), "desviados": len(desviados), "parchados": puestos,
                      "como_salto_en_tablas": saltos,
                      "apis_nuevas": sum(len(f) for _, _, _, f in nuevas),
                      "dlls_nuevas": [d for d, _, _, _ in nuevas],
                      "sin_call": no_eran, "tirados_por_imposibles": len(getattr(self, "tirados", {})),
                      "por_lectura_del_stub": len(getattr(self, "por_lectura", {})),
                      "fuente": getattr(self, "fuente", "-"),
                      "sin_resolver": len(desviados) - len(parches)}


# ---------- ★ el control ----------
def control():
    v = Volcado()
    ok = True

    def chequear(n, c, d=""):
        nonlocal ok
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok = ok and c

    print("control sobre", v.dir)
    # 1) el resolvedor tiene que acertar un caso de respuesta conocida: la dirección que la propia
    #    tabla de exports de kernel32 da para un nombre, tiene que volver con ESE nombre.
    k = next((m for m in v.mods if m["nombre"].lower() == "kernel32.dll"), None)
    chequear("kernel32 está en modulos.json", bool(k))
    # ⚠ el error del 08-nov: leer la DLL de 64 bits. El tamaño en disco tiene que dar igual
    #    que el que el módulo ocupa en memoria, si no los RVA no significan nada.
    malas = [m["nombre"] for m in v.res.mods if not v.res.ruta_real(m)]
    chequear("cada DLL de disco coincide con la de memoria", not malas, str(malas[:6]))
    if k:
        v.res._tabla(k)
        rva = v.res.por_nombre["kernel32.dll"].get("CreateFileA")
        r = v.res(k["base"] + rva) if rva else None
        chequear("resuelve una API conocida", bool(r) and r[1] == "CreateFileA", str(r))
        # control al revés: una dirección en medio de kernel32 que no es el principio de ningún
        # export no tiene que devolver nombre (el esperado se deriva: rva+1)
        chequear("NO inventa un nombre para una dirección que no es un export",
                 v.res(k["base"] + rva + 1) is None)
    chequear("NO resuelve una dirección fuera de toda DLL", v.res(0x12345678) is None)
    s, sn = v.slots()
    chequear("encuentra casilleros de import", len(s) > 100, "(%d con nombre, %d sin)" % (len(s), len(sn)))
    dlls = {}
    for dll, fn in s.values():
        dlls[dll] = dlls.get(dll, 0) + 1
    print("   por DLL:", dict(sorted(dlls.items(), key=lambda x: -x[1])[:10]))
    va, por = v.oep()
    # ⚠ el 0x7E3A11 que usa `construir` está medido en la corrida 4 y confirmado de la forma más
    #   dura que hay: el exe reconstruido ARRANCA con él. Este control sirve para ver si la
    #   búsqueda por APIs cae en la misma función; si se separara mucho, uno de los dos está mal.
    cerca = bool(va) and abs(va - 0x7E3A11) < 0x400
    chequear("encuentra el arranque del juego", cerca,
             "%s (%s) · el que se usa es 0x7e3a11, a %d bytes"
             % (hex(va) if va else "-", por, abs((va or 0) - 0x7E3A11)))
    print("  →", "TODO BIEN" if ok else "ALGO FALLA")
    return v, ok


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "control"
    if cmd == "control":
        return 0 if control()[1] else 1
    v = Volcado()
    if cmd == "iat":
        s, sn = v.slots()
        print("%d casilleros con nombre, %d sin resolver" % (len(s), len(sn)))
        for x in sorted(s)[:40]:
            print("  %08x -> %s!%s" % (x, s[x][0], s[x][1]))
        for x in sorted(sn)[:20]:
            print("  %08x -> ??? %08x" % (x, sn[x]))
    elif cmd == "construir":
        ruta, inf = v.construir()
        print("→ %s" % ruta)
        for k in sorted(inf):
            print("   %-14s %s" % (k, inf[k]))
    elif cmd == "oep":
        va, por = v.oep()
        print("arranque original (OEP): %s   [%s]" % (hex(va) if va else "no encontrado", por))
        if va:
            for i in list(v.md.disasm(bytes(v.img[va - BASE:va - BASE + 0x50]), va))[:14]:
                print("  %08x  %s %s" % (i.address, i.mnemonic, i.op_str))
    else:
        sys.exit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
