r"""version_cliente -- ★ (21-nov) LA REGLA DE VERSIONES del cliente que reparte el launcher, y sus NOVEDADES.

Usa el sistema que YA existe (no inventa otro):
  · la RELEASE del cliente = `version` del manifiesto `eda.json` (armar_cliente.py), «AAAA.MM.DD.N». El launcher guarda
    la última que aceptó («eda_ver_ok») y RECHAZA una menor (firmar_manifiesto.py): por eso cada publicación tiene que
    SUBIR la versión;
  · la DLL = `herramientas/dll_d3d9/VERSION` (x.y.z) + commit y build, que la dll lleva adentro («EDA-ID|v=…|c=…|s=…»,
    identificar.py).
Y agrega lo que faltaba: `NOVEDADES.json` (en la raíz del repo), UNA entrada por release con lo que verá el jugador.

    py herramientas\version_cliente.py revisar NUEVO\eda.json [ANTERIOR\eda.json] [--carpeta CLIENTE_REPARTIR]
        ANTES DE FIRMAR. Para si algo no cumple la regla. Dice: versión anterior y nueva, archivos que cambian (y los que
        NO se van a bajar), la dll que va (versión, commit, ¿sucia?), y el texto del POP-UP.
    py herramientas\version_cliente.py novedades NUEVO\eda.json
        agrega al manifiesto el bloque «novedades» de su versión (va FIRMADO con el resto: ver documentacion/VERSIONES.md)
    py herramientas\version_cliente.py popup VERSION        el texto del POP-UP de esa versión
    py herramientas\version_cliente.py noticia VERSION      ★ la NOTICIA del panel que el launcher abre sola después de instalar
    py herramientas\version_cliente.py control              las pruebas (con sus reveses)

La regla (que `revisar` hace cumplir):
  1. la versión nueva es «AAAA.MM.DD.N» y MAYOR que la anterior;
  2. tiene su entrada en NOVEDADES.json, completa y NO «borrador»: fecha, resumen; y corregidos / mejoras / avisos;
  3. algo cambia (si ningún archivo cambia, no hay nada que publicar);
  4. si cambia d3d9.dll: su marca EDA-ID está, NO es una compilación sucia, y su VERSION (x.y.z) es MAYOR que la de la
     release anterior; y es la que dice la entrada de NOVEDADES («dll»);
  5. si cambia EDA_limpio.exe: avisa (su md5 es la clave del protocolo: el server tiene que conocerla antes);
  6. los archivos del usuario (autoexec.cfg, eda_d3d9.ini) no se pisan (el launcher los baja sólo si faltan).
Los cambios SÓLO del server no pasan por acá: se identifican por su commit de despliegue (actualizaciones.log del VPS).
"""
import hashlib
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOVEDADES = os.path.join(RAIZ, "NOVEDADES.json")
DEL_USUARIO = ("autoexec.cfg", "eda_d3d9.ini")
MARCA = re.compile(rb"EDA-ID\|v=([0-9.]{1,16})\|c=([0-9A-Za-z-]{1,40})\|s=([01])\|f=([^|\x00]{1,40})\|b=([0-9A-Za-z-]{1,40})\|")
VERSION = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})(?:\.(\d{1,3}))?$")
# ★ (21-nov 19:30) lo que el launcher YA aceptó: «2026.11.19» y «2026.11.21» (tres números, en launcher.json eda_ver_ok).
#   El launcher trae la biblioteca `semver` de Rust, que sólo acepta TRES números y sin ceros a la izquierda: si la usa
#   para la versión de EDA, «2026.11.22.1» (cuatro) o «2026.12.05» (cero) darían «número de versión inválido» y no se
#   bajaría nada. Hasta que el dueño del launcher confirme cómo la compara, `revisar` lo AVISA.
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
LIMITES = {"resumen": 280, "item": 160, "items": 8}


class Regla(Exception):
    pass


def v_release(v):
    m = VERSION.match(str(v))
    if not m:
        raise Regla("versión «%s»: va AAAA.MM.DD.N (p. ej. 2026.11.22.1) o AAAA.MM.DD (la que publicó TEST el 21-nov)" % v)
    return tuple(int(x or 0) for x in m.groups())          # (sin .N = .0: 2026.11.21 < 2026.11.21.1 < 2026.11.22)


def v_dll(v):
    return tuple(int(x) for x in str(v).split("."))


def leer_novedades(ruta=NOVEDADES):
    d = json.load(open(ruta, encoding="utf-8"))
    return {e["version"]: e for e in d.get("versiones", [])}


def entrada_valida(e):
    """Los problemas de una entrada de NOVEDADES.json (lista vacía = sirve)."""
    p = []
    if e.get("borrador"):
        p.append("está como «borrador»: no se publica")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(e.get("fecha", ""))):
        p.append("falta la fecha (AAAA-MM-DD)")
    if not e.get("resumen") or len(e["resumen"]) > LIMITES["resumen"]:
        p.append("el resumen falta o pasa de %d letras" % LIMITES["resumen"])
    listas = [k for k in ("corregidos", "mejoras", "avisos") if e.get(k)]
    if not listas:
        p.append("no dice nada: corregidos, mejoras o avisos")
    for k in ("corregidos", "mejoras", "avisos"):
        v = e.get(k, [])
        if not isinstance(v, list) or len(v) > LIMITES["items"] or any(
                not isinstance(x, str) or not x.strip() or len(x) > LIMITES["item"] for x in v):
            p.append("«%s»: hasta %d frases de hasta %d letras" % (k, LIMITES["items"], LIMITES["item"]))
    if any(re.search(r"<[a-zA-Z/]", x) for k in ("resumen",) for x in [e.get(k, "")]) or any(
            re.search(r"<[a-zA-Z/]", x) for k in ("corregidos", "mejoras", "avisos") for x in e.get(k, [])):
        p.append("sin HTML: el launcher lo muestra como texto")
    return p


def marca_dll(ruta):
    if not ruta or not os.path.exists(ruta):
        return None
    m = MARCA.search(open(ruta, "rb").read())
    if not m:
        return None
    v, c, s, f, b = (x.decode("ascii", "replace") for x in m.groups())
    return {"version": v, "commit": c, "sucia": s == "1", "fecha": f, "build": b}


def archivos(man):
    return {f["path"]: f for f in man.get("files", [])}


def revisar(nuevo, anterior=None, carpeta=None, novedades=None):
    """→ (problemas, informe en texto). problemas vacío = se puede firmar."""
    novedades = leer_novedades() if novedades is None else novedades
    p, info = [], []
    try:
        vn = v_release(nuevo["version"])
    except Regla as e:
        return [str(e)], ""
    va = None
    if anterior:
        try:
            va = v_release(anterior["version"])
        except Regla as e:
            p.append("la anterior: %s" % e)
        if va and vn <= va:
            p.append("la versión nueva (%s) no es MAYOR que la anterior (%s): el launcher la rechazaría"
                     % (nuevo["version"], anterior["version"]))
    info.append("Versión anterior: %s" % (anterior["version"] if anterior else "(ninguna dada)"))
    info.append("Versión nueva:    %s" % nuevo["version"])
    if not SEMVER.match(str(nuevo["version"])):
        info.append("⚠ «%s» no tiene la forma de las que el launcher ya aceptó (tres números sin ceros a la izquierda, "
                    "como 2026.11.21): confirmar con el dueño del launcher que la compara bien antes de publicar"
                    % nuevo["version"])
    e = novedades.get(nuevo["version"])
    if not e:
        p.append("NOVEDADES.json no tiene la entrada de %s" % nuevo["version"])
    else:
        p += ["NOVEDADES %s: %s" % (nuevo["version"], x) for x in entrada_valida(e)]
    a, n = archivos(anterior or {}), archivos(nuevo)
    cambian = sorted(k for k in n if k not in a or a[k].get("md5") != n[k].get("md5"))
    se_van = sorted(k for k in a if k not in n)
    iguales = sorted(k for k in n if k in a and a[k].get("md5") == n[k].get("md5"))
    if anterior and not cambian and not se_van:
        p.append("ningún archivo cambia: no hay nada que publicar")
    info.append("Archivos que cambian (%d): %s" % (len(cambian), ", ".join(cambian) or "—"))
    if se_van:
        info.append("Archivos que ya no van: %s" % ", ".join(se_van))
    info.append("No se vuelven a bajar (iguales): %d" % len(iguales))
    for u in DEL_USUARIO:
        if u in cambian and u in a:
            info.append("ⓘ %s cambia, pero es del usuario: el launcher lo baja SÓLO si falta (no pisa el suyo)" % u)
    if "EDA_limpio.exe" in cambian and anterior:
        p.append("EDA_limpio.exe cambia: su md5 es la CLAVE del protocolo. Primero el server tiene que conocerla "
                 "(EDA_CLAVES) y después se publica; si es a propósito, publicar con --exe-a-proposito")
    if "d3d9.dll" in cambian:
        md = marca_dll(os.path.join(carpeta, "d3d9.dll")) if carpeta else None
        if not carpeta:
            p.append("d3d9.dll cambia: falta --carpeta (la del cliente a repartir) para leer su versión")
        elif not md:
            p.append("la d3d9.dll a repartir no tiene la marca EDA-ID: es vieja o no es nuestra")
        else:
            real = hashlib.md5(open(os.path.join(carpeta, "d3d9.dll"), "rb").read()).hexdigest()
            if real != n["d3d9.dll"].get("md5"):
                p.append("la d3d9.dll de la carpeta no es la del manifiesto (md5 %s ≠ %s)" % (real, n["d3d9.dll"]["md5"]))
            if md["sucia"]:
                p.append("la d3d9.dll es una compilación SUCIA (cambios sin commitear): no se reparte")
            if e and e.get("dll") and e["dll"] != md["version"]:
                p.append("NOVEDADES dice dll %s y la dll es %s" % (e["dll"], md["version"]))
            ant = novedades.get(anterior["version"], {}).get("dll") if anterior else None
            if ant and v_dll(md["version"]) <= v_dll(ant):
                p.append("la dll cambia pero su VERSION (%s) no es MAYOR que la de la release anterior (%s): subir "
                         "herramientas/dll_d3d9/VERSION" % (md["version"], ant))
            info.append("d3d9.dll: EDA %s · commit %s · build %s · %s" % (md["version"], md["commit"], md["build"],
                                                                         "SUCIA" if md["sucia"] else "limpia"))
    if e:
        info.append("")
        info.append(texto_popup(e))
    return p, "\n".join(info)


def texto_popup(e):
    t = ["── POP-UP ─────────────────────────────",
         "EDA %s · %s" % (e["version"], e.get("fecha", "?")), "", e.get("resumen", "")]
    for k, nombre in (("avisos", "⚠ Importante"), ("corregidos", "Corregido"), ("mejoras", "Mejoras")):
        if e.get(k):
            t.append("")
            t.append(nombre + ":")
            t += ["  • " + x for x in e[k]]
    t.append("───────────────────────────────────────")
    return "\n".join(t)


def noticia(e):
    """★ (21-nov) el POP-UP del launcher de R2Beat: una NOTICIA del panel (`launcher_contenido`) con el formato de
    noticias.js (# título, - lista, **negrita**; todo se escapa allá). El id `eda-<versión>` y la etiqueta `parche` son
    los que abre solo launcher/popup-novedades/novedades.js después de instalar (una vez: `noticias_vistas`)."""
    t = ["**Nueva versión instalada: EDA %s**" % e["version"]]
    if e.get("resumen"):
        t.append(e["resumen"])
    for k, nombre in (("corregidos", "Errores corregidos"), ("mejoras", "Mejoras"), ("avisos", "Avisos importantes")):
        if e.get(k):
            t += ["", "# " + nombre] + ["- " + x for x in e[k]]
    return {"id": "eda-%s" % e["version"], "juego": "eda", "etiqueta": "parche", "fijada": False, "imagen": "",
            "fecha": e.get("fecha", ""), "titulo": "EDA %s: nueva versión instalada" % e["version"], "texto": "\n".join(t)}


def bloque_novedades(e):
    """lo que va en el manifiesto (texto plano, sin HTML: el launcher lo pinta)"""
    return {k: e[k] for k in ("version", "fecha", "resumen", "corregidos", "mejoras", "avisos") if k in e}


def control():
    import tempfile
    ok = []

    def chequear(t, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", t, d))
        ok.append(bool(c))
    t = tempfile.mkdtemp()
    dll = os.path.join(t, "d3d9.dll")

    def poner_dll(v, sucia=False):
        cuerpo = b"MZ...EDA-ID|v=%s|c=abc1234|s=%d|f=2026-11-22 10:00 UTC|b=b0123456789|..." % (v.encode(), sucia)
        open(dll, "wb").write(cuerpo)
        return hashlib.md5(cuerpo).hexdigest()
    nov = {"2026.11.19.1": {"version": "2026.11.19.1", "fecha": "2026-11-19", "dll": "0.5.0", "resumen": "Antes.",
                            "mejoras": ["algo"]},
           "2026.11.22.1": {"version": "2026.11.22.1", "fecha": "2026-11-22", "dll": "0.5.1",
                            "resumen": "Arreglo de una caída en las stages.",
                            "corregidos": ["El juego ya no se cierra solo en algunas stages (0x7F4626)."],
                            "avisos": ["Si el juego se cerraba en una stage, vuelvan a probarla."]}}
    viejo = {"version": "2026.11.19.1", "files": [{"path": "Data.dat", "md5": "a" * 32, "size": 1},
                                                  {"path": "d3d9.dll", "md5": "b" * 32, "size": 1},
                                                  {"path": "eda_d3d9.ini", "md5": "c" * 32, "size": 1}]}

    def nuevo(v="2026.11.22.1", dll_md5=None, extra=None):
        fs = [{"path": "Data.dat", "md5": "a" * 32, "size": 1}, {"path": "d3d9.dll", "md5": dll_md5 or "b" * 32, "size": 1},
              {"path": "eda_d3d9.ini", "md5": "c" * 32, "size": 1}] + (extra or [])
        return {"version": v, "files": fs}
    m = poner_dll("0.5.1")
    p, info = revisar(nuevo(dll_md5=m), viejo, t, nov)
    chequear("una release correcta (versión mayor, novedades completas, dll nueva y limpia) pasa", not p, p)
    chequear("…y dice la versión anterior, la nueva, qué cambia y qué NO se baja",
             "Versión anterior: 2026.11.19.1" in info and "Archivos que cambian (1): d3d9.dll" in info
             and "No se vuelven a bajar (iguales): 2" in info)
    chequear("…y el texto del POP-UP con la versión, la fecha y lo corregido",
             "EDA 2026.11.22.1 · 2026-11-22" in info and "Corregido:" in info and "⚠ Importante" in info)
    p, _ = revisar(nuevo("2026.11.19.1", m), viejo, t, nov)
    chequear("★ el revés: la MISMA versión que la anterior → no (el launcher la rechazaría)",
             any("no es MAYOR" in x for x in p))
    p, _ = revisar(nuevo("2026.11.18.9", m), viejo, t, nov)
    chequear("★ el revés: una versión MENOR → no", any("no es MAYOR" in x for x in p))
    p, info = revisar(nuevo(dll_md5=m), dict(viejo, version="2026.11.21"), t, nov)
    chequear("la anterior con el formato que publicó TEST (2026.11.21, tres números) se acepta y compara bien",
             not p and "⚠ «2026.11.22.1» no tiene la forma" in info, p)
    p, _ = revisar(nuevo("2026.11.21", m), dict(viejo, version="2026.11.21.1"), t, nov)
    chequear("★ el revés: 2026.11.21 es MENOR que 2026.11.21.1", any("no es MAYOR" in x for x in p))
    p, _ = revisar(nuevo("22-nov", m), viejo, t, nov)
    chequear("★ el revés: una versión con otro formato → no", any("AAAA.MM.DD.N" in x for x in p))
    p, _ = revisar(nuevo("2026.11.22.2", m), viejo, t, nov)
    chequear("★ el revés: sin su entrada en NOVEDADES.json → no", any("no tiene la entrada" in x for x in p))
    borr = dict(nov, **{"2026.11.22.1": dict(nov["2026.11.22.1"], borrador=True)})
    p, _ = revisar(nuevo(dll_md5=m), viejo, t, borr)
    chequear("★ el revés: una entrada «borrador» → no", any("borrador" in x for x in p))
    p, _ = revisar(nuevo(), viejo, t, nov)
    chequear("★ el revés: nada cambia → no hay nada que publicar", any("ningún archivo cambia" in x for x in p))
    m2 = poner_dll("0.5.0")
    p, _ = revisar(nuevo(dll_md5=m2), viejo, t, dict(nov, **{"2026.11.22.1": dict(nov["2026.11.22.1"], dll="0.5.0")}))
    chequear("★ el revés: la dll cambia pero su VERSION no sube → no", any("no es MAYOR que la de la release" in x for x in p))
    m3 = poner_dll("0.5.1", sucia=True)
    p, _ = revisar(nuevo(dll_md5=m3), viejo, t, nov)
    chequear("★ el revés: una dll SUCIA (cambios sin commitear) → no", any("SUCIA" in x for x in p))
    poner_dll("0.5.1")
    p, _ = revisar(nuevo(dll_md5="d" * 32), viejo, t, nov)
    chequear("★ el revés: la dll de la carpeta no es la del manifiesto (un archivo viejo) → no",
             any("no es la del manifiesto" in x for x in p))
    open(dll, "wb").write(b"MZ sin marca")
    p, _ = revisar(nuevo(dll_md5=hashlib.md5(b"MZ sin marca").hexdigest()), viejo, t, nov)
    chequear("★ el revés: una dll sin EDA-ID (vieja) → no", any("EDA-ID" in x for x in p))
    m = poner_dll("0.5.1")
    _, info = revisar(nuevo(dll_md5=m), dict(viejo, files=viejo["files"] + [{"path": "viejo.txt", "md5": "e" * 32}]), t, nov)
    chequear("si un archivo deja de ir, se dice (no se calla)", "Archivos que ya no van: viejo.txt" in info, info[:200])
    ex = nuevo(dll_md5=m)
    ex["files"].append({"path": "EDA_limpio.exe", "md5": "f" * 32, "size": 1})
    p, _ = revisar(ex, dict(viejo, files=viejo["files"] + [{"path": "EDA_limpio.exe", "md5": "e" * 32, "size": 1}]), t, nov)
    chequear("★ el exe cambia → se frena (su md5 es la clave del protocolo)", any("CLAVE del protocolo" in x for x in p))
    malo = dict(nov["2026.11.22.1"], mejoras=["<script>x</script>"])
    chequear("★ el revés: HTML en las novedades → no", any("sin HTML" in x for x in entrada_valida(malo)))
    largo = dict(nov["2026.11.22.1"], resumen="x" * 400)
    chequear("★ el revés: un resumen de más de %d letras → no" % LIMITES["resumen"], any("resumen" in x for x in entrada_valida(largo)))
    b = bloque_novedades(nov["2026.11.22.1"])
    chequear("el bloque del manifiesto lleva sólo texto (sin «dll» ni «borrador»)",
             set(b) == {"version", "fecha", "resumen", "corregidos", "avisos"})
    n = noticia(nov["2026.11.22.1"])
    chequear("la noticia del POP-UP: id eda-<versión>, juego eda, etiqueta parche, y en orden: versión, corregidos, avisos",
             n["id"] == "eda-2026.11.22.1" and n["juego"] == "eda" and n["etiqueta"] == "parche"
             and n["texto"].index("Nueva versión instalada") < n["texto"].index("# Errores corregidos")
             < n["texto"].index("# Avisos importantes") and "# Mejoras" not in n["texto"])
    real = leer_novedades()
    chequear("NOVEDADES.json del repo se lee y cada entrada publicada es válida",
             all(not entrada_valida(e) for e in real.values() if not e.get("borrador")))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main(a):
    if a[:1] == ["control"]:
        return control()
    if a[:1] == ["popup"] and len(a) == 2:
        e = leer_novedades().get(a[1])
        if not e:
            raise SystemExit("⛔ NOVEDADES.json no tiene %s" % a[1])
        print(texto_popup(e))
        return 0
    if a[:1] == ["noticia"] and len(a) == 2:
        e = leer_novedades().get(a[1])
        if not e:
            raise SystemExit("⛔ NOVEDADES.json no tiene %s" % a[1])
        print(json.dumps(noticia(e), ensure_ascii=False, indent=1))
        return 0
    if a[:1] == ["novedades"] and len(a) == 2:
        m = json.load(open(a[1], encoding="utf-8"))
        e = leer_novedades().get(m["version"])
        if not e or entrada_valida(e):
            raise SystemExit("⛔ la entrada de %s no sirve: %s" % (m["version"], entrada_valida(e) if e else "falta"))
        m["novedades"] = bloque_novedades(e)
        json.dump(m, open(a[1], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print("★ %s: novedades de %s agregadas (se firman con el resto)" % (a[1], m["version"]))
        return 0
    if a[:1] == ["revisar"] and len(a) >= 2:
        carpeta = None
        if "--carpeta" in a:
            i = a.index("--carpeta")
            carpeta = a[i + 1]
            a = a[:i] + a[i + 2:]
        exe_ok = "--exe-a-proposito" in a
        a = [x for x in a if x != "--exe-a-proposito"]
        nuevo = json.load(open(a[1], encoding="utf-8"))
        anterior = json.load(open(a[2], encoding="utf-8")) if len(a) > 2 else None
        p, info = revisar(nuevo, anterior, carpeta)
        if exe_ok:
            p = [x for x in p if "CLAVE del protocolo" not in x]
        print(info)
        print()
        if p:
            print("⛔ NO se puede publicar todavía:")
            for x in p:
                print("  · " + x)
            return 1
        print("✅ cumple la regla: se puede firmar (firmar_manifiesto.py) y subir")
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
