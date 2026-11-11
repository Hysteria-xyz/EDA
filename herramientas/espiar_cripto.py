r"""espiar_cripto -- poner breakpoints en las API de cifrado y de red DENTRO del juego andando,
y anotar sus argumentos: con qué cadena se hashea, qué clave se deriva, qué se cifra y qué sale.

★ Para qué (10-nov): el primer paquete al Broker son 72 bytes, **idénticos en cada corrida**
  (`espiar_broker.py`). Algo constante cifrado con algo constante. El exe tiene la cadena
  CryptoAPI completa (MD5 → `CryptDeriveKey(CALG_RC4)`), y leerla estática es lento porque las
  llamadas desviadas desalinean el desensamblado. Medir es más corto: un `int3` al entrar de cada
  API, se leen los argumentos, y para las que DEVUELVEN datos (`CryptEncrypt`, `CryptDecrypt`,
  `CryptGetHashParam`, `recv`) otro `int3` de un solo uso en la dirección de vuelta.

    py herramientas\espiar_cripto.py                  # 20 s de EDA_limpio.exe
    py herramientas\espiar_cripto.py --segundos 30 --exe EDA_limpio.exe

Deja `_trabajo/broker/cripto.log`.

⚠ Los breakpoints van en **cryptsp.dll** (donde Windows tiene de verdad las Crypt*; las de
  advapi32 son reenvíos) y en **ws2_32.dll**. Cada llamada se anota con quién la hizo (las
  direcciones del exe que hay en la pila).
⚠ Sin ASProtect no hay anti-debug (`probar_libre.py` corre igual), pero el exe parchado se sigue
  muriendo a los ~12 s por las llamadas sin resolver: el Broker se intenta a los ~1,6 s, alcanza.
★ El control: si `espiar_broker.py` está corriendo, lo que este programa ve salir por `send` tiene
  que ser IDÉNTICO a lo que el oyente guardó en su `con_NNN.bin` — dos herramientas que miden lo
  mismo por caminos distintos. Y el revés: el texto que entra a `CryptEncrypt` NO tiene que ser
  igual a lo que sale (si lo fuera, no hubo cifrado y la hipótesis se cae).
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import glob
import os
import struct
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from probar_libre import SI, PI, EXR, DBG, CTX, hilo_de      # noqa: E402

import pefile                                                # noqa: E402

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
SALIDA = os.path.join(RAIZ, "_trabajo", "broker")
LOG = os.path.join(SALIDA, "cripto.log")
WOW = r"C:\Windows\SysWOW64"
EXCEPCION, SALIDA_PROC, CARGA_DLL = 1, 5, 6
SEGUIR, NO_MANEJADA = 0x00010002, 0x80010001
BP_CODIGOS = (0x80000003, 0x4000001F)        # int3 (nativo y WOW64)
PASO_CODIGOS = (0x80000004, 0x4000001E)      # paso a paso (nativo y WOW64)

# dll -> {función: cuántos argumentos leer}
MIRAR = {
    "cryptsp.dll": {"CryptCreateHash": 5, "CryptHashData": 4, "CryptDeriveKey": 5,
                    "CryptImportKey": 6, "CryptEncrypt": 7, "CryptDecrypt": 6,
                    "CryptGetHashParam": 5, "CryptGenKey": 4, "CryptExportKey": 6},
    "ws2_32.dll": {"send": 4, "recv": 4, "WSASend": 7, "connect": 3,
                   # ★ el UDP de la partida, a CUALQUIER destino (el espía sólo ve el del Broker)
                   "sendto": 6, "WSASendTo": 9, "bind": 3},
    "kernelbase.dll": {"CreateFileA": 7, "CreateFileW": 7},
    # ★ quién decide cerrar el juego (sale con código 0 a los ~10 s de conectar, corrida 16)
    "user32.dll": {"PostQuitMessage": 1, "MessageBoxA": 4, "MessageBoxW": 4},
}
# ★ y dentro del propio exe: el rand/srand de la CRT de MSVC (leídos en el desensamblado: el LCG
#   214013/2531011 = 0x343FD/0x269EC3, con la semilla por hilo en `_getptd()+0x14`).
#   La hipótesis que esto prueba: el hola del Broker sale IGUAL en cada corrida porque usa rand()
#   en un hilo que nadie sembró — y quien lo sembraba con la hora era el código de GameGuard
#   (`0x7CF716`: `srand(timeGetTime())`), que la receta `limpio` corta.
EXE_MIRAR = {0x7DD820: ("srand", 1), 0x7DD82D: ("rand", 0),
             0x7F1043: ("swprintf", 4)}       # ★ _woutput: el núcleo de TODOS los wprintf
FORMATOS_A_MIRAR = ("LV", "Lv", "%d/%d", "%d / %d", "EXP")
SEGUIR_TRAMPAS = bool(os.environ.get("EDA_SEGUIR"))   # EDA_SEGUIR=1: listar y saltear las trampas
# ★ el objeto de cifrado de la red (leído en `0x750B90..0x750CDB`, ver MEDICIONES corrida 15):
#   se anotan genéricamente — argumentos, lo que apunta cada uno y qué cambió a la vuelta.
EXE_FUNCIONES = {
    0x74C900: 4, 0x74C930: 3, 0x74C8C0: 1,        # el objeto de red carga clave / RSA / versión
    0x750CA0: 2, 0x6242E0: 1,                     # crea el contexto de cifrado con 0xA5C2A2B6
    0x7A99F0: 4,                                  # le pone la clave (clave, 16, 3, contexto)
    0x750BE0: 4, 0x750C30: 4,                     # los dos cifrados por bloques (12 y 16)
    0x624140: 5, 0x624200: 5,                     # lo que hay debajo de cada uno
    0x750C70: 4, 0x750C80: 4,                     # el RSA de juguete (cifrar / descifrar)
}
EXE_FUNCIONES.update({
    0x624990: 2,                                  # ★ ruta del exe -> texto hexa de 32 = la CLAVE AES
    0x624CB0: 1,                                  #   (y quien lo pasa a 16 bytes con "%2x")
    0x74CE00: 2,                                  # el descifrado de AES (sólo corre si llegó algo)
    0x43AA40: 1,                                  # ★ «cerrar con mensaje»: arg1 = el texto
    0x40FC40: 0,                                  # ★ ILTClient::Shutdown() (sin mensaje): QUIÉN
    0x549300: 1,                                  # ENTER de la lista (arg1 = el elegido)
    0x64CD90: 1, 0x64BFE0: 1, 0x64CC50: 0,        # ★ la lista de escenarios: SCENARIOLISTXML, CHAPTERS
    0x6209F0: 1,                                  # ★ ¿el escenario N está disponible? (mapa de terminados)
    0x510D50: 1, 0x5343D0: 4, 0x5345C0: 0,        # ★ la escena de carga, su aviso (cmd 1) y su paso
    0x5496C0: 1,                                  # el manejador del 0x1010
    0x4E7350: 1,                                  # cambia de pantalla (arg1 = cuál)
    # ⚠ NO `0x744910` ni `0x74D260`: el ruteador los llama en CADA cuadro, llegue algo o no
})
for _va, _n in EXE_FUNCIONES.items():
    EXE_MIRAR[_va] = ("exe:%08x" % _va, _n)
# ★ PUNTOS en el medio de una función: el `call [edx+N]` del ruteador del Broker (`0x4E5690..`),
#   con `ecx` = el objeto que va a atender y `[esp]` = el paquete ya descifrado. NO llevan
#   breakpoint de vuelta (`[esp]` no es una dirección de retorno: es el paquete).
EXE_PUNTOS = {0x4E56E7: 0x34,                     # comandos 0x1003..0x100B -> [esi+0x44]
              0x4E570A: 0x04}                     # todo lo demás -> la pantalla actual [esi+0x48]
for _va, _off in EXE_PUNTOS.items():
    EXE_MIRAR[_va] = ("punto:%08x" % _va, 0)
ALGS = {0x8003: "CALG_MD5", 0x8004: "CALG_SHA1", 0x6801: "CALG_RC4", 0x6602: "CALG_RC2",
        0x6610: "CALG_AES_256", 0x660E: "CALG_AES_128", 0xA400: "CALG_RSA_KEYX",
        0x2400: "CALG_RSA_SIGN", 0x6603: "CALG_3DES", 0x6601: "CALG_DES"}

_log = None


def log(m=""):
    print(m, flush=True)
    _log.write(m + "\n")
    _log.flush()


def hexa(d, sangria="      "):
    out = []
    for i in range(0, len(d), 16):
        t = d[i:i + 16]
        out.append("%s%04x  %-48s |%s|" % (sangria, i, " ".join("%02x" % c for c in t),
                                           "".join(chr(c) if 32 <= c < 127 else "." for c in t)))
    return "\n".join(out) if out else sangria + "(vacío)"


def exports(dll):
    """{nombre: rva} de la DLL de 32 bits, leída de disco."""
    pe = pefile.PE(os.path.join(WOW, dll), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    out = {}
    for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if s.name and not s.forwarder:
            out[s.name.decode()] = s.address
    return out


class Depurador:
    def __init__(self, exe):
        self.exe = exe
        self.bps = {}            # va -> (byte original, nombre, n args)   permanentes
        self.vueltas = {}        # va -> byte original                    de un solo uso
        self.pend = {}           # (tid, va de vuelta) -> (nombre, args)
        self.rearmar = {}        # tid -> va a re-armar después del paso a paso
        self.hilos = {}
        self.envios = []         # bytes de cada send, para el control
        self.trampas = []        # sitios sin resolver alcanzados (con EDA_SEGUIR=1)
        self.cifrados = []       # (entra, sale) de cada CryptEncrypt, para el revés
        self.rands = {}          # (hilo, quién) -> cuántas veces
        self.tiempo_rand = {}    # hilo -> [(t, quién)] (los últimos)
        self.hilo_red = {}       # hilo -> "connect"/"send" y cuándo
        self.t0 = time.time()

    # ------------------------------------------------------------ memoria
    def leer(self, va, n):
        if not va or n <= 0:
            return b""
        b = ctypes.create_string_buffer(n)
        g = ctypes.c_size_t(0)
        k32.ReadProcessMemory(self.h, ctypes.c_void_p(va), b, n, ctypes.byref(g))
        return b.raw[:g.value]

    def u32(self, va):
        d = self.leer(va, 4)
        return struct.unpack("<I", d)[0] if len(d) == 4 else 0

    def escribir(self, va, d):
        g = ctypes.c_size_t(0)
        viejo = wt.DWORD(0)
        k32.VirtualProtectEx(self.h, ctypes.c_void_p(va), len(d), 0x40, ctypes.byref(viejo))
        ok = k32.WriteProcessMemory(self.h, ctypes.c_void_p(va), d, len(d), ctypes.byref(g))
        k32.VirtualProtectEx(self.h, ctypes.c_void_p(va), len(d), viejo.value, ctypes.byref(viejo))
        k32.FlushInstructionCache(self.h, ctypes.c_void_p(va), len(d))
        return ok

    def poner(self, va):
        orig = self.leer(va, 1)
        self.escribir(va, b"\xcc")
        return orig

    # ------------------------------------------------------------ contexto
    def ctx(self, hh):
        c = CTX()
        c.ContextFlags = 0x10001 | 0x10002
        k32.Wow64GetThreadContext(hh, ctypes.byref(c))
        return c

    def quien(self, esp):
        """Las direcciones del código del exe que hay en la pila: quién llamó."""
        d = self.leer(esp, 0x180)
        r = [struct.unpack_from("<I", d, i)[0] for i in range(0, len(d) - 3, 4)]
        return [v for v in r if 0x401000 <= v < 0x88A000][:5]

    # ------------------------------------------------------------ cada API
    def al_entrar(self, nombre, a, ret, tid, callers):
        quien = " ".join("%08x" % v for v in callers)
        t = time.time() - self.t0
        if nombre == "rand":
            self.rands[(tid, ret)] = self.rands.get((tid, ret), 0) + 1
            self.tiempo_rand.setdefault(tid, []).append((t, ret))
            self.tiempo_rand[tid] = self.tiempo_rand[tid][-40:]
            return None
        if nombre == "srand":
            log("  %5.1fs  srand(%08x)  hilo %d   (de %s)" % (t, a[0], tid, quien))
            return None
        if nombre in ("send", "WSASend", "connect"):
            self.hilo_red.setdefault(tid, []).append((nombre, t))
        if nombre == "swprintf":
            # ★ todo texto de la interfaz pasa por acá: se anota sólo el que interesa
            fmt = self.leer(a[1], 120).decode("utf-16-le", "replace").split("\0")[0]
            if any(k in fmt for k in FORMATOS_A_MIRAR):
                vals = [self.u32(a[3] + 4 * i) for i in range(4)]   # a[3] = el va_list
                log("%5.1fs  ★ swprintf %r  args %s   (de %s)"
                    % (t, fmt, " ".join("%08x" % v for v in vals), quien))
            return None
        if nombre.startswith("punto:"):
            va = int(nombre[6:], 16)
            ecx = self.ultimo_ecx
            vt = self.u32(ecx)
            destino = self.u32(vt + EXE_PUNTOS[va])
            paquete = ret                                    # acá [esp] es el paquete
            buf = self.u32(paquete + 0x100C)
            d = self.leer(buf, 96)
            cmd = struct.unpack_from("<H", d, 2)[0] if len(d) >= 4 else -1
            log("%5.1fs  ★★ RUTEADOR %08x: comando %04x -> objeto %08x (vtable %08x) -> %08x\n%s"
                % (t, va, cmd, ecx, vt, destino, hexa(d)))
            return None
        if nombre.startswith("exe:"):
            # genérico: los argumentos, y lo que hay detrás de cada uno que sea un puntero
            ecx = self.ultimo_ecx
            log("%5.1fs  %s  ecx=%08x  args %s   (de %s)"
                % (t, nombre, ecx, " ".join("%08x" % x for x in a), quien))
            antes = {}
            for i, x in enumerate([ecx] + a):
                d = self.leer(x, 96) if 0x10000 <= x < 0x7FFF0000 else b""
                if d:
                    antes[i] = (x, d)
                    log("      %s -> %08x\n%s" % ("ecx " if i == 0 else "arg%d" % i, x,
                                                  hexa(d, "        ")))
            return (nombre, a, antes)
        if nombre == "CryptCreateHash":
            log("CryptCreateHash  %s   (de %s)" % (ALGS.get(a[1], hex(a[1])), quien))
        elif nombre == "CryptHashData":
            d = self.leer(a[1], min(a[2], 4096))
            log("CryptHashData  %d bytes   (de %s)\n%s" % (a[2], quien, hexa(d)))
        elif nombre == "CryptDeriveKey":
            log("CryptDeriveKey  %s  flags %08x (largo de clave %d bits)   (de %s)"
                % (ALGS.get(a[1], hex(a[1])), a[3], a[3] >> 16, quien))
        elif nombre == "CryptImportKey":
            d = self.leer(a[1], min(a[2], 4096))
            log("CryptImportKey  %d bytes  flags %08x   (de %s)\n%s" % (a[2], a[4], quien, hexa(d)))
        elif nombre == "CryptGenKey":
            log("CryptGenKey  %s  flags %08x   (de %s)" % (ALGS.get(a[1], hex(a[1])), a[2], quien))
        elif nombre == "CryptExportKey":
            log("CryptExportKey  tipo %d   (de %s)" % (a[2], quien))
        elif nombre in ("CryptEncrypt", "CryptDecrypt"):
            n = self.u32(a[5])
            d = self.leer(a[4], min(n, 4096))
            log("%s  final=%d  %d bytes ENTRAN   (de %s)\n%s" % (nombre, a[2], n, quien, hexa(d)))
            return (nombre, a, d)
        elif nombre == "CryptGetHashParam":
            return (nombre, a, None)
        elif nombre == "send":
            d = self.leer(a[1], min(a[2], 65536))
            self.envios.append(d)
            log("★ send  socket %x  %d bytes   (de %s)\n%s" % (a[0], a[2], quien, hexa(d)))
        elif nombre == "WSASend":
            partes = b""
            for i in range(min(a[2], 16)):
                ln, buf = self.u32(a[1] + i * 8), self.u32(a[1] + i * 8 + 4)
                partes += self.leer(buf, min(ln, 65536))
            self.envios.append(partes)
            log("★ WSASend  socket %x  %d bytes   (de %s)\n%s"
                % (a[0], len(partes), quien, hexa(partes)))
        elif nombre == "PostQuitMessage":
            log("%5.1fs  ★★ PostQuitMessage(%d)  hilo %d   (de %s)" % (t, a[0], tid, quien))
        elif nombre in ("MessageBoxA", "MessageBoxW"):
            def txt(p):
                raw = self.leer(p, 400)
                return (raw.decode("utf-16-le", "replace").split("\0")[0] if nombre[-1] == "W"
                        else raw.split(b"\0")[0].decode("cp949", "replace"))
            log("%5.1fs  ★★ %s  título %r  texto %r   (de %s)"
                % (t, nombre, txt(a[2]), txt(a[1]), quien))
        elif nombre in ("CreateFileA", "CreateFileW"):
            if callers:                                      # sólo las que pide el exe
                raw = self.leer(a[0], 520)
                ruta = (raw.decode("utf-16-le", "replace").split("\0")[0] if nombre[-1] == "W"
                        else raw.split(b"\0")[0].decode("latin1"))
                log("%5.1fs  %s %r  acceso %08x   (de %s)" % (t, nombre, ruta, a[1], quien))
        elif nombre == "sendto":
            d = self.leer(a[1], min(a[2], 512))
            sa = self.leer(a[4], 16)
            dest = ("%s:%d" % (".".join(str(x) for x in sa[4:8]), struct.unpack(">H", sa[2:4])[0])
                    if len(sa) >= 8 else "?")
            log("%5.1fs  ★ UDP sendto %s  %d bytes   (de %s)\n%s" % (t, dest, a[2], quien, hexa(d)))
        elif nombre == "WSASendTo":
            ln, buf = self.u32(a[1]), self.u32(a[1] + 4)
            d = self.leer(buf, min(ln, 512))
            sa = self.leer(a[5], 16)
            dest = ("%s:%d" % (".".join(str(x) for x in sa[4:8]), struct.unpack(">H", sa[2:4])[0])
                    if len(sa) >= 8 else "?")
            log("%5.1fs  ★ UDP WSASendTo %s  %d bytes   (de %s)\n%s" % (t, dest, ln, quien, hexa(d)))
        elif nombre == "bind":
            sa = self.leer(a[1], 16)
            if len(sa) >= 8:
                log("%5.1fs  bind %s:%d   (de %s)" % (t, ".".join(str(x) for x in sa[4:8]),
                                                    struct.unpack(">H", sa[2:4])[0], quien))
        elif nombre == "connect":
            sa = self.leer(a[1], 16)
            if len(sa) >= 8:
                ip = ".".join(str(x) for x in sa[4:8])
                log("connect  %s:%d   (de %s)" % (ip, struct.unpack(">H", sa[2:4])[0], quien))
        elif nombre == "recv":
            return (nombre, a, None)
        return None

    def al_volver(self, info, eax):
        nombre, a, entra = info
        if nombre == "exe:00624990":
            # arg1 es un std::string de MSVC 2005: largo en +0x14, capacidad en +0x18, y el
            # texto adentro (+4) si la capacidad es < 16, o apuntado desde +4 si no
            o = a[0]
            largo, cap = self.u32(o + 0x14), self.u32(o + 0x18)
            txt = self.leer(o + 4 if cap < 16 else self.u32(o + 4), min(largo, 200))
            log("      ★ 0x624990 devolvió el texto (%d): %r" % (largo, txt))
        if nombre.startswith("exe:"):
            log("      %s volvió  eax=%08x" % (nombre, eax))
            for i, (x, d) in entra.items():
                ahora = self.leer(x, 96)
                if ahora != d:
                    log("      ★ CAMBIÓ %s -> %08x\n%s" % ("ecx " if i == 0 else "arg%d" % i, x,
                                                         hexa(ahora, "        ")))
            return
        if nombre in ("CryptEncrypt", "CryptDecrypt"):
            n = self.u32(a[5])
            d = self.leer(a[4], min(n, 4096))
            log("%s  devolvió %d  %d bytes SALEN\n%s" % (nombre, eax, n, hexa(d)))
            if nombre == "CryptEncrypt":
                self.cifrados.append((entra, d))
        elif nombre == "CryptGetHashParam":
            n = self.u32(a[3])
            log("CryptGetHashParam  param %d  -> %s" % (a[1], self.leer(a[2], n).hex(" ")
                                                        if a[2] else "(pide el largo: %d)" % n))
        elif nombre == "recv":
            if eax and eax < 0x80000000:
                log("★ recv  %d bytes\n%s" % (eax, hexa(self.leer(a[1], eax))))

    # ------------------------------------------------------------ el bucle
    def cargó(self, ev):
        crudo = bytes(ev.u.crudo)
        hfile, base = struct.unpack_from("<QQ", crudo, 0)
        nom = ctypes.create_unicode_buffer(600)
        if hfile:
            k32.GetFinalPathNameByHandleW(ctypes.c_void_p(hfile), nom, 600, 0)
            k32.CloseHandle(ctypes.c_void_p(hfile))
        ruta = nom.value.lower()
        if "syswow64" not in ruta:
            return
        dll = os.path.basename(ruta)
        if dll not in MIRAR:
            return
        ex = exports(dll)
        puestos = []
        for fn, n in MIRAR[dll].items():
            if fn not in ex:
                log("  ⚠ %s no exporta %s" % (dll, fn))
                continue
            va = base + ex[fn]
            self.bps[va] = (self.poner(va), fn, n)
            puestos.append(fn)
        log("  [bp] %s en %08x: %s" % (dll, base, ", ".join(puestos)))

    def correr(self, segundos):
        si = SI()
        si.cb = ctypes.sizeof(si)
        pi = PI()
        if not k32.CreateProcessW(self.exe, None, None, None, False, 2, None,
                                  os.path.dirname(self.exe), ctypes.byref(si), ctypes.byref(pi)):
            sys.exit("[!] no pude lanzar %s (error %d)" % (self.exe, ctypes.get_last_error()))
        self.h = pi.hProcess
        self.hilos[pi.dwTid] = pi.hThread
        log("★ %s  pid %d  (%d s)" % (os.path.basename(self.exe), pi.dwPid, segundos))
        ev = DBG()
        t0 = self.t0 = time.time()
        cuenta, ultimo = {}, t0
        while time.time() - t0 < segundos:
            if time.time() - ultimo > 5:
                ultimo = time.time()
                log("  %5.1fs  (eventos hasta acá: %s)" % (ultimo - t0, cuenta))
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 50):
                continue
            cuenta[ev.code] = cuenta.get(ev.code, 0) + 1
            seguir = SEGUIR
            if ev.code == 3:                                 # el proceso nació: el exe ya está
                for va, (fn, n) in EXE_MIRAR.items():
                    self.bps[va] = (self.poner(va), fn, n)
                log("  [bp] en el exe: %s" % ", ".join(
                    "%s %08x" % (fn, va) for va, (fn, _) in EXE_MIRAR.items()))
            elif ev.code == CARGA_DLL:
                self.cargó(ev)
            elif ev.code == SALIDA_PROC:
                log("  %5.1fs  el juego terminó, código %08x"
                    % (time.time() - t0, struct.unpack_from("<I", bytes(ev.u.crudo), 0)[0]))
                break
            elif ev.code == EXCEPCION:
                e = ctypes.cast(ctypes.byref(ev.u), ctypes.POINTER(EXR)).contents
                va = (e.addr or 0) & 0xFFFFFFFF
                hh = hilo_de(ev.tid, self.hilos)
                if e.code in BP_CODIGOS and (va in self.bps or va in self.vueltas):
                    self.en_bp(va, ev.tid, hh)
                elif e.code in PASO_CODIGOS and ev.tid in self.rearmar:
                    self.escribir(self.rearmar.pop(ev.tid), b"\xcc")
                elif e.code in PASO_CODIGOS:
                    log("  ⚠ paso a paso de un hilo que no esperaba (%d) en %08x" % (ev.tid, va))
                elif e.code in BP_CODIGOS or e.code == 0x40010006:
                    pass                                     # el del cargador / OutputDebugString
                elif (SEGUIR_TRAMPAS and e.code == 0xC0000005
                      and 0xD0000000 <= va < 0xD0600000 and hh):
                    # ★ una llamada desviada SIN resolver: se anota y se saltea (EAX = 0, como
                    #   si la API hubiera fallado), para que UNA corrida liste todas. ⚠ lo que
                    #   pase después ya no es confiable (la pila puede quedar corrida)
                    sitio = va - 0xD0000000 + 0x400000
                    if sitio not in self.trampas:
                        self.trampas.append(sitio)
                        log("  %5.1fs  ★ TRAMPA %08x (sin resolver) — la salteo"
                            % (time.time() - t0, sitio))
                    from probar_libre import saltear_trampa
                    saltear_trampa(self.h, hh)
                else:
                    log("  %5.1fs  excepción %08x en %08x (no es nuestra)"
                        % (time.time() - t0, e.code, va))
                    # ★ y para un C0000005: registros + quién llamó (la pila de ESE momento; la
                    #   del .dmp del juego sale pisada por su propio manejador de crashes)
                    if e.code in (0xC0000005, 0xE06D7363) and hh:   # AV, y un `throw` de C++
                        c = self.ctx(hh)
                        log("           eax=%08x ebx=%08x ecx=%08x edx=%08x esi=%08x edi=%08x "
                            "ebp=%08x esp=%08x" % (c.Eax, c.Ebx, c.Ecx, c.Edx, c.Esi, c.Edi,
                                                    c.Ebp, c.Esp))
                        d = self.leer(c.Esp, 0x8000)   # ⚠ 0x57F9A0 sola tiene 9,5 KB de locales
                        rets = [struct.unpack_from("<I", d, i)[0] for i in range(0, len(d) - 3, 4)]
                        log("           pila (código del exe): %s" % " ".join(
                            "%08x" % v for v in rets if 0x401000 <= v < 0x88A000)[:1200])
                    seguir = NO_MANEJADA
            k32.ContinueDebugEvent(ev.pid, ev.tid, seguir)
        k32.TerminateProcess(pi.hProcess, 1)

    def en_bp(self, va, tid, hh):
        c = self.ctx(hh)
        c.Eip = va                                           # deshacer el int3
        if va in self.bps:
            orig, nombre, n = self.bps[va]
            self.ultimo_ecx = c.Ecx                          # el `this` de los thiscall
            self.ultimo_esp = c.Esp
            ret = self.u32(c.Esp)
            a = [self.u32(c.Esp + 4 + 4 * i) for i in range(n)]
            info = self.al_entrar(nombre, a, ret, tid, self.quien(c.Esp))
            if info is not None and ret:
                if ret not in self.vueltas and ret not in self.bps:
                    self.vueltas[ret] = self.poner(ret)
                self.pend[(tid, ret)] = info
            # sacar el int3, dar UN paso y volver a ponerlo
            self.escribir(va, orig)
            c.EFlags |= 0x100
            self.rearmar[tid] = va
        if va in self.vueltas:
            info = self.pend.pop((tid, va), None)
            if info:
                self.al_volver(info, c.Eax)
            if not any(k[1] == va for k in self.pend):
                self.escribir(va, self.vueltas.pop(va))
            else:                                            # otro hilo también vuelve acá
                self.escribir(va, self.vueltas[va])
                c.EFlags |= 0x100
                self.rearmar[tid] = va
        k32.Wow64SetThreadContext(hh, ctypes.byref(c))


def main():
    global _log
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="EDA_limpio.exe")
    ap.add_argument("--segundos", type=int, default=20)
    a = ap.parse_args()
    os.makedirs(SALIDA, exist_ok=True)
    _log = open(LOG, "a", encoding="utf-8")
    log("\n===== %s =====" % time.strftime("%Y-%m-%d %H:%M:%S"))
    exe = a.exe if os.path.isabs(a.exe) else os.path.join(JUEGO, a.exe)
    d = Depurador(exe)
    antes = set(glob.glob(os.path.join(SALIDA, "con_*.bin")))
    d.correr(a.segundos)

    log("\n— trampas alcanzadas (sitios SIN resolver): %s"
        % (" ".join("%08x" % x for x in d.trampas) or "ninguna"))
    log("\n— rand() por hilo (★ = el hilo que sale a la red) —")
    for tid in sorted(set(k[0] for k in d.rands)):
        marca = "★ %s" % d.hilo_red[tid] if tid in d.hilo_red else ""
        quienes = sorted(((n, q) for (h, q), n in d.rands.items() if h == tid), reverse=True)
        log("  hilo %6d  %5d llamadas  %s" % (tid, sum(n for n, _ in quienes), marca))
        for n, q in quienes[:8]:
            log("      %5d  desde %08x" % (n, q))
        if tid in d.hilo_red:
            red = [t for _, t in d.hilo_red[tid]]
            log("      las últimas antes de la red: %s" % ", ".join(
                "%.2fs@%08x" % (t, q) for t, q in d.tiempo_rand[tid] if t <= max(red))[-400:])
    for tid in d.hilo_red:
        if tid not in set(k[0] for k in d.rands):
            log("  hilo %6d  ★ %s  — NO llamó a rand() ni una vez" % (tid, d.hilo_red[tid]))

    log("\n— los controles —")
    nuevos = sorted(set(glob.glob(os.path.join(SALIDA, "con_*.bin"))) - antes)
    if nuevos and d.envios:
        oyente = open(nuevos[-1], "rb").read()
        igual = any(e == oyente for e in d.envios) or b"".join(d.envios) == oyente
        log("  %s lo que sale por send es IDÉNTICO a lo que guardó el oyente (%s, %d bytes)"
            % ("✅" if igual else "⛔", os.path.basename(nuevos[-1]), len(oyente)))
    else:
        log("  ℹ sin cruce con el oyente (¿está corriendo `espiar_broker.py`?)  envíos=%d"
            % len(d.envios))
    for entra, sale in d.cifrados:
        log("  %s CryptEncrypt cambió los datos (%d bytes)"
            % ("✅" if entra != sale else "⛔ NO", len(entra)))
    _log.close()


if __name__ == "__main__":
    main()
