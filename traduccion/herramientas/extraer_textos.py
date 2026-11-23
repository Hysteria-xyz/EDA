r"""extraer_textos -- extrae el inventario completo de cadenas de EDA a `_trabajo/textos-en.json`.

Uso:
    python traduccion/herramientas/extraer_textos.py generar [--cliente RUTA] [--desempacado RUTA]
    python traduccion/herramientas/extraer_textos.py control [--cliente RUTA] [--desempacado RUTA]

Fuentes que recorre (todas en solo lectura):
  1. `_trabajo/traduccion_desempacado/` (XML de Data.dat): UIString, Err_String, NameAndExplainString,
     MapNameAndExplainString, Chapter1_string, ChatFilter.
  2. `menu/international/*.xml`: mapea cada STRID a su pantalla y caja de píxeles
     (W, H, FONTSIZE) para estimar `largo_max` y riesgo de desborde en español (+25-30 %).
  3. `LTMsg.dll`: tabla de recursos RT_STRING (28 mensajes del motor LithTech; solo lectura).
  4. `exe/EDA_limpio.exe`: cadenas visibles al jugador incrustadas en el ejecutable.
  5. `servidor/*.py`: mensajes enviados al jugador por chat/avisos.
"""
import argparse
import ast
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[2]
CARPETA_DESEMPACADO = RAIZ_REPO / "_trabajo" / "traduccion_desempacado"
SALIDA_JSON = RAIZ_REPO / "_trabajo" / "textos-en.json"

# Ancho promedio de glifo en ARIAL.TTF (~0.55 * fontsize) y alto de línea (~1.25 * fontsize)
FACTOR_ANCHO_GLIFO = 0.55
FACTOR_ALTO_LINEA = 1.25
EXPANSION_ES = 1.28  # +28 % promedio del español respecto al inglés

BLOQUES_MAP = [
    ("nombre", "Selector de Stage / Sala (Nombre del mapa)"),
    ("historia", "Selector de Stage / Sala (Historia / Briefing)"),
    ("objetivo", "Selector de Stage / Sala (Objetivo de misión)"),
    ("nivel", "Selector de Stage / Sala (Nivel recomendado)"),
    ("historia_ko_legado", "Selector de Stage (Copia coreana legada, sin usar)"),
]

BLOQUES_NAME_EXPLAIN = [
    ("nombre", "Tienda / Inventario / Habilidades / Combate (Nombre)"),
    ("descripcion", "Tienda / Inventario / Habilidades / Personaje (Descripción)"),
]

PANTALLA_POR_RANGO_UI = [
    (0, 999, "General / Popups / Común"),
    (1000, 1999, "ServerSelect (Selección de servidor)"),
    (2000, 2999, "CharacterSelect (Selección y creación de personaje)"),
    (3000, 3999, "ChannelLobby (Lobby, canales, crear sala, buscar)"),
    (4000, 4999, "WaitRoom (Sala de espera)"),
    (5000, 5999, "ShopNInventory (Tienda, inventario, refinería, habilidades)"),
    (6000, 6999, "GameScene (HUD en partida, muerte, resultados)"),
]

PANTALLA_POR_RANGO_ERR = [
    (0, 99, "Conexión / Servidor / Login"),
    (100, 199, "CharacterSelect (Creación / borrado de personaje)"),
    (200, 299, "ShopNInventory / Refinería / Habilidades"),
    (300, 399, "ChannelLobby / Salas / Canales"),
    (400, 499, "WaitRoom (Sala de espera / Invitaciones)"),
]

# Cadenas visibles al jugador verificadas en EDA_limpio.exe (UTF-16-LE referenciadas por lógica de juego)
CADENAS_EXE_VISIBLES = [
    (0x899700, "LV%3d", "Lobby / Sala / HUD", "Nivel del personaje en formato compacto"),
    (0x899F94, "%dGold", "Tienda / Inventario / HUD", "Precio o saldo en oro"),
    (0x899FA4, "%dCash", "Tienda (obsoleto en economía solo oro)", "Precio en cash"),
    (0x899FB4, "[%s]%s(%dGold)", "Tienda / Confirmación de compra", "Formato de ítem en lista de compra"),
    (0x899C10, "/w", "Chat (Lobby / Sala / Partida)", "Prefijo de comando de susurro"),
    (0x899100, "FPS:%5d", "HUD / Diagnóstico", "Contador de cuadros por segundo"),
    (0x899110, "dt:%.3f", "HUD / Diagnóstico", "Delta de tiempo entre cuadros"),
    (0x899CA4, "%s X %d\\n", "Resultados / Recompensas", "Cantidad de ítem ganado"),
]


def _buscar_cliente(cliente: Path | None) -> Path | None:
    candidatos = []
    if cliente:
        candidatos.append(Path(cliente))
    if os.environ.get("EDA_CLIENTE"):
        candidatos.append(Path(os.environ["EDA_CLIENTE"]))
    candidatos += [
        RAIZ_REPO / "_trabajo" / "juego",
        RAIZ_REPO / "cliente",
        RAIZ_REPO.parent.parent / "EDA-Pristino",
    ]
    for c in candidatos:
        if (c / "LTMsg.dll").is_file():
            return c
    return None


def _buscar_desempacado(desempacado: Path | None) -> Path:
    candidatos = []
    if desempacado:
        candidatos.append(Path(desempacado))
    if os.environ.get("EDA_TRADUCCION_DESEMPACADO"):
        candidatos.append(Path(os.environ["EDA_TRADUCCION_DESEMPACADO"]))
    candidatos += [
        CARPETA_DESEMPACADO,
        RAIZ_REPO.parent.parent / "pruebas" / "laboratorio" / "traduccion" / "desempacado",
    ]
    for c in candidatos:
        if (c / "string" / "international" / "uistring.xml").is_file():
            return c
    raise SystemExit("⛔ No encontré los XML desempacados. Corre primero desempacar_data_dat.py extraer")


def _detectar_idioma(texto: str) -> str:
    if any(0xAC00 <= ord(c) <= 0xD7A3 for c in texto):
        return "ko"
    sin_fmt = re.sub(r"%[-+0-9.]*[dfsuxX%]|\\n", "", texto)
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{2,}", sin_fmt):
        return "formato"
    return "en"


def _notas_placeholders(texto: str) -> list[str]:
    notas = []
    phs = re.findall(r"%[-+0-9.]*[dfsuxX%s]|%\d+![ds]!", texto)
    if phs:
        notas.append("Placeholders: " + ", ".join(phs))
    if "\\n" in texto:
        notas.append("Usa \\n para salto de línea")
    if "<" in texto or ">" in texto:
        notas.append("Contiene < o > sin escapar en el XML original (TinyXML lo tolera)")
    if any(0xAC00 <= ord(c) <= 0xD7A3 for c in texto):
        notas.append("Texto en coreano sin traducir en el cliente original")
    return notas


def _pantalla_por_rango(idx_str: str, rangos: list[tuple[int, int, str]]) -> str:
    try:
        n = int(idx_str.strip())
    except ValueError:
        return "Desconocida"
    for lo, hi, nombre in rangos:
        if lo <= n <= hi:
            return nombre
    return "Desconocida"


def _parsear_bloques_stringinfo(xml_path: Path) -> list[list[tuple[str, str, str | None, int]]]:
    """Parsea todos los bloques <STRINGINFO> de un XML tolerando `<` sin escapar en VALUE."""
    txt = xml_path.read_bytes().decode("utf-8-sig", errors="replace")
    sin_com = re.sub(r"<!--.*?-->", "", txt, flags=re.S)
    bloques_raw = re.findall(r"<STRINGINFO[^>]*>(.*?)</STRINGINFO>", sin_com, flags=re.S | re.I)
    if not bloques_raw:
        bloques_raw = [sin_com]
    pat_str = re.compile(
        r'<STRING\s+INDEX="([^"]*)"\s+VALUE="([^"]*)"(?:\s+VALUE2="([^"]*)")?\s*/?>',
        re.I,
    )
    res = []
    for br in bloques_raw:
        items = []
        for pos, m in enumerate(pat_str.finditer(br)):
            items.append((m.group(1).strip(), m.group(2), m.group(3), pos))
        res.append(items)
    return res


def cargar_cajas_menu(desempacado: Path) -> tuple[dict[str, list[dict]], list[dict]]:
    """Lee todos los menu/international/*.xml y devuelve (strid_cajas, imagenes_sin_xml)."""
    try:
        from PIL import Image
    except ImportError:
        Image = None

    strid_cajas: dict[str, list[dict]] = {}
    tex_map: dict[str, dict] = {}
    menu_dir = desempacado / "menu" / "international"

    for mp in sorted(menu_dir.glob("*.xml")):
        txt = mp.read_bytes().decode("utf-8-sig", errors="replace")
        safe = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", txt)
        try:
            tree = ET.fromstring(safe)
        except ET.ParseError:
            continue

        rootpath = ""
        id_to_tex: dict[str, tuple[str, str]] = {}
        t_node = tree.find("TEXTURES")
        if t_node is not None:
            rootpath = t_node.attrib.get("ROOTPATH", "").replace("\\\\", "/").replace("\\", "/").strip("/")
            for tel in t_node.findall("TEXTURE"):
                tid = tel.attrib.get("ID", "")
                tp = tel.attrib.get("PATH", "").replace("\\\\", "/").replace("\\", "/").lstrip("/")
                full = f"{rootpath}/{tp}" if rootpath else tp
                id_to_tex[tid] = (full, tel.attrib.get("EXPLAIN", "").strip())

        for el in tree.iter():
            if el.tag in ("TEXTURE", "TEXTURES"):
                continue
            a = el.attrib
            sid = (a.get("STRID") or a.get("TEXTID") or a.get("STRINGID") or "").strip()
            if sid and sid != "0":
                w = int(a["W"]) if a.get("W", "").isdigit() and int(a["W"]) > 0 else None
                h = int(a["H"]) if a.get("H", "").isdigit() and int(a["H"]) > 0 else None
                fs = int(a["FONTSIZE"]) if a.get("FONTSIZE", "").isdigit() and int(a["FONTSIZE"]) > 0 else None
                strid_cajas.setdefault(sid, []).append({
                    "pantalla": mp.name,
                    "control": el.tag,
                    "w": w,
                    "h": h,
                    "fontsize": fs,
                })
            tid = a.get("TEXID")
            if tid and tid in id_to_tex:
                full, explain = id_to_tex[tid]
                key = full.lower()
                rec = tex_map.setdefault(key, {
                    "ruta": full,
                    "pantallas": set(),
                    "controles_strid0": set(),
                    "controles_strid_nz": set(),
                    "strids": set(),
                    "descripciones_dev": set(),
                })
                rec["pantallas"].add(mp.name)
                if explain:
                    rec["descripciones_dev"].add(explain)
                if sid and sid != "0":
                    rec["controles_strid_nz"].add(el.tag)
                    rec["strids"].add(sid)
                else:
                    rec["controles_strid0"].add(el.tag)

    disk = {
        p.relative_to(desempacado).as_posix().lower(): p
        for p in desempacado.rglob("*")
        if p.is_file()
    }
    imagenes_sin_xml = []
    for key, rec in sorted(tex_map.items()):
        p = disk.get(key)
        if not p or rec["controles_strid_nz"]:
            continue
        sz = p.stat().st_size
        w, h = 0, 0
        if Image is not None:
            try:
                with Image.open(p) as im:
                    w, h = im.size
            except Exception:
                pass
        imagenes_sin_xml.append({
            "ruta": p.relative_to(desempacado).as_posix(),
            "tam_bytes": sz,
            "ancho": w,
            "alto": h,
            "pantallas": sorted(rec["pantallas"]),
            "controles": sorted(rec["controles_strid0"]),
            "descripcion_dev": " / ".join(sorted(rec["descripciones_dev"])),
        })
    return strid_cajas, imagenes_sin_xml


def _evaluar_caja(texto: str, cajas: list[dict]) -> tuple[int | None, dict | None, str | None]:
    """Calcula capacidad estimada más estricta y nivel de riesgo para español (+28 %)."""
    mejor = None
    for c in cajas:
        if not (c["w"] and c["fontsize"]):
            continue
        if c["w"] <= 20 and c["h"] and c["h"] <= 20:
            continue
        lineas = max(1, (c["h"] or c["fontsize"]) // max(1, int(c["fontsize"] * FACTOR_ALTO_LINEA)))
        cap = max(1, int((c["w"] / (c["fontsize"] * FACTOR_ANCHO_GLIFO)) * lineas))
        llenado_en = len(texto) / cap
        if mejor is None or llenado_en > mejor[0]:
            mejor = (llenado_en, cap, {
                "pantalla": c["pantalla"],
                "control": c["control"],
                "w": c["w"],
                "h": c["h"],
                "fontsize": c["fontsize"],
                "lineas": lineas,
                "cap_estimada_chars": cap,
                "llenado_en_pct": round(llenado_en * 100, 1),
                "llenado_es_est_pct": round(llenado_en * EXPANSION_ES * 100, 1),
            })
    if mejor is None:
        return None, None, None
    llenado_en, cap, info = mejor
    if llenado_en * EXPANSION_ES >= 1.0:
        riesgo = "alto"
    elif llenado_en * EXPANSION_ES >= 0.8:
        riesgo = "medio"
    else:
        riesgo = "bajo"
    return cap, info, riesgo


def extraer_ltmsg(cliente: Path | None) -> list[dict]:
    if not cliente or not (cliente / "LTMsg.dll").is_file():
        return []
    import pefile
    lt_path = cliente / "LTMsg.dll"
    pe = pefile.PE(str(lt_path), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
    out = []
    for rt in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if rt.id != 6:  # RT_STRING
            continue
        for entry in rt.directory.entries:
            block_id = entry.id
            for lang in entry.directory.entries:
                data = pe.get_data(lang.data.struct.OffsetToData, lang.data.struct.Size)
                pos = 0
                for i in range(16):
                    if pos + 2 > len(data):
                        break
                    slen = struct.unpack_from("<H", data, pos)[0]
                    pos += 2
                    if slen > 0:
                        s = data[pos : pos + slen * 2].decode("utf-16-le", errors="replace")
                        sid = (block_id - 1) * 16 + i
                        out.append({
                            "id": f"ltmsg:{sid}",
                            "origen": "LTMsg.dll (RT_STRING)",
                            "bloque": "motor_lithtech",
                            "pantalla": "Errores fatales del motor LithTech",
                            "idioma_origen": "en",
                            "texto_en": s,
                            "largo_en": len(s),
                            "largo_max": 499,
                            "caja_px": None,
                            "riesgo_desborde": "bajo",
                            "notas": _notas_placeholders(s) + [
                                "NO modificar LTMsg.dll en disco: su MD5 es la clave AES de Data.dat"
                            ],
                        })
                        pos += slen * 2
    pe.close()
    return out


def extraer_exe(cliente: Path | None) -> list[dict]:
    exe_path = RAIZ_REPO / "exe" / "EDA_limpio.exe"
    if not exe_path.is_file() and cliente:
        exe_path = cliente / "EDA_limpio.exe"
    if not exe_path.is_file():
        return []
    exe = exe_path.read_bytes()
    base = 0x400000
    out = []
    for va, esperado, pantalla, desc in CADENAS_EXE_VISIBLES:
        off = va - base
        raw = exe[off : off + len(esperado.replace("\\n", "\n")) * 2]
        leido = raw.decode("utf-16-le", errors="replace").replace("\n", "\\n")
        assert leido == esperado, f"EXE {hex(va)}: esperado {esperado!r}, leído {leido!r}"
        out.append({
            "id": f"exe:0x{va:06x}",
            "origen": "EDA_limpio.exe (.rdata UTF-16-LE)",
            "bloque": "exe_hardcoded",
            "pantalla": pantalla,
            "idioma_origen": _detectar_idioma(esperado),
            "texto_en": esperado,
            "largo_en": len(esperado),
            "largo_max": len(esperado),
            "caja_px": None,
            "riesgo_desborde": "medio",
            "notas": _notas_placeholders(esperado) + [desc, "Parchar solo en memoria desde d3d9.dll (nunca en disco)"],
        })
    return out


def extraer_servidor() -> list[dict]:
    """Extrae cadenas literales enviadas a clientes desde servidor/*.py del repo."""
    srv_dir = RAIZ_REPO / "servidor"
    out = []
    vistos: set[tuple[str, str]] = set()
    for p in sorted(srv_dir.glob("*.py")):
        if p.name in ("pruebas.py", "diag.py"):
            continue
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=p.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if fn not in ("_aviso", "aviso", "linea_chat") or not node.args:
                continue
            arg0 = node.args[0]
            texto = None
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                texto = arg0.value
            elif isinstance(arg0, ast.BinOp) and isinstance(arg0.op, ast.Mod) and isinstance(arg0.left, ast.Constant) and isinstance(arg0.left.value, str):
                texto = arg0.left.value
            elif isinstance(arg0, ast.JoinedStr):
                texto = ast.get_source_segment(src, arg0)
            if not texto or (p.name, texto) in vistos:
                continue
            vistos.add((p.name, texto))
            idioma = "es"
            if any(w in texto for w in ("Requests", "Friends", "Item {")):
                idioma = "es_con_en"
            out.append({
                "id": f"srv:{p.stem}:L{node.lineno}",
                "origen": f"servidor/{p.name} (L{node.lineno})",
                "bloque": "servidor_chat",
                "pantalla": "Chat del sistema / Messenger / Comandos GM",
                "idioma_origen": idioma,
                "texto_en": texto,
                "largo_en": len(texto),
                "largo_max": 200,
                "caja_px": None,
                "riesgo_desborde": "bajo",
                "notas": ["Ya está en español en el server" if idioma == "es" else "En español con término en inglés a unificar"],
            })
    return out


def construir_inventario(desempacado: Path, cliente: Path | None) -> dict:
    strid_cajas, imagenes_sin_xml = cargar_cajas_menu(desempacado)
    cadenas: list[dict] = []

    bloques_ui = _parsear_bloques_stringinfo(desempacado / "string/international/uistring.xml")
    vistos_ui: Counter = Counter()
    for idx, val, _v2, _pos in bloques_ui[0]:
        if not val.strip():
            continue
        vistos_ui[idx] += 1
        sid = f"ui:{idx}" if vistos_ui[idx] == 1 else f"ui:{idx}#{vistos_ui[idx]}"
        cajas = strid_cajas.get(idx, [])
        pantallas = sorted(set(c["pantalla"] for c in cajas))
        pantalla = ", ".join(pantallas) if pantallas else _pantalla_por_rango(idx, PANTALLA_POR_RANGO_UI)
        lmax, caja_px, riesgo = _evaluar_caja(val, cajas)
        cadenas.append({
            "id": sid,
            "origen": "Data.dat:string/international/uistring.xml",
            "bloque": "ui",
            "pantalla": pantalla,
            "idioma_origen": _detectar_idioma(val),
            "texto_en": val,
            "largo_en": len(val),
            "largo_max": lmax,
            "caja_px": caja_px,
            "riesgo_desborde": riesgo,
            "notas": _notas_placeholders(val),
        })

    bloques_err = _parsear_bloques_stringinfo(desempacado / "string/international/err_string.xml")
    for idx, val, _v2, _pos in bloques_err[0]:
        if not val.strip():
            continue
        cadenas.append({
            "id": f"err:{idx}",
            "origen": "Data.dat:string/international/err_string.xml",
            "bloque": "error",
            "pantalla": _pantalla_por_rango(idx, PANTALLA_POR_RANGO_ERR),
            "idioma_origen": _detectar_idioma(val),
            "texto_en": val,
            "largo_en": len(val),
            "largo_max": 160,
            "caja_px": None,
            "riesgo_desborde": "medio" if len(val) > 100 else "bajo",
            "notas": _notas_placeholders(val),
        })

    bloques_ne = _parsear_bloques_stringinfo(desempacado / "string/international/nameandexplainstring.xml")
    for b_idx, items in enumerate(bloques_ne):
        b_cod, b_pant = BLOQUES_NAME_EXPLAIN[b_idx] if b_idx < len(BLOQUES_NAME_EXPLAIN) else (f"b{b_idx}", "Ítems/Habilidades")
        vistos_ne: Counter = Counter()
        for idx, val, _v2, _pos in items:
            if not val.strip():
                continue
            vistos_ne[idx] += 1
            sid = f"item:{b_cod}:{idx}" if vistos_ne[idx] == 1 else f"item:{b_cod}:{idx}#{vistos_ne[idx]}"
            notas = _notas_placeholders(val)
            if vistos_ne[idx] > 1:
                notas.append(f"INDEX={idx} duplicado en el XML original de Softnyx")
            cadenas.append({
                "id": sid,
                "origen": "Data.dat:string/international/nameandexplainstring.xml",
                "bloque": f"item_{b_cod}",
                "pantalla": b_pant,
                "idioma_origen": _detectar_idioma(val),
                "texto_en": val,
                "largo_en": len(val),
                "largo_max": 32 if b_cod == "nombre" else 280,
                "caja_px": None,
                "riesgo_desborde": "medio" if (b_cod == "nombre" and len(val) > 22) or (b_cod == "descripcion" and len(val) > 190) else "bajo",
                "notas": notas,
            })

    bloques_map = _parsear_bloques_stringinfo(desempacado / "string/international/mapnameandexplainstring.xml")
    for b_idx, items in enumerate(bloques_map):
        b_cod, b_pant = BLOQUES_MAP[b_idx] if b_idx < len(BLOQUES_MAP) else (f"b{b_idx}", "Mapas")
        for idx, val, _v2, _pos in items:
            if not val.strip():
                continue
            cadenas.append({
                "id": f"map:{b_cod}:{idx}",
                "origen": "Data.dat:string/international/mapnameandexplainstring.xml",
                "bloque": f"map_{b_cod}",
                "pantalla": b_pant,
                "idioma_origen": _detectar_idioma(val),
                "texto_en": val,
                "largo_en": len(val),
                "largo_max": 45 if b_cod == "nombre" else (240 if b_cod == "historia" else None),
                "caja_px": None,
                "riesgo_desborde": "medio" if (b_cod == "nombre" and len(val) > 32) or (b_cod == "historia" and len(val) > 180) else "bajo",
                "notas": _notas_placeholders(val),
            })

    bloques_ch1 = _parsear_bloques_stringinfo(
        desempacado / "data/scenario/string/international/chapter1_string.xml"
    )
    vistos_ch1: Counter = Counter()
    for idx, val, _v2, _pos in bloques_ch1[0]:
        if not val.strip():
            continue
        vistos_ch1[idx] += 1
        sid = f"scen:{idx}" if vistos_ch1[idx] == 1 else f"scen:{idx}#{vistos_ch1[idx]}"
        stage_num = idx[:2] if len(idx) == 4 else (idx[:3] if len(idx) == 5 else "?")
        cadenas.append({
            "id": sid,
            "origen": "Data.dat:data/scenario/string/international/chapter1_string.xml",
            "bloque": "escenario_ch1",
            "pantalla": f"GameScene — Diálogos/objetivos en Stage (grupo {stage_num})",
            "idioma_origen": _detectar_idioma(val),
            "texto_en": val,
            "largo_en": len(val),
            "largo_max": 180,
            "caja_px": None,
            "riesgo_desborde": "medio" if len(val) > 130 else "bajo",
            "notas": _notas_placeholders(val),
        })

    bloques_cf = _parsear_bloques_stringinfo(
        desempacado / "data/unusablechaandfiltering/international/chatfilter.xml"
    )
    for idx, val, v2, _pos in bloques_cf[0]:
        if not val.strip():
            continue
        cadenas.append({
            "id": f"filter:{idx}",
            "origen": "Data.dat:data/unusablechaandfiltering/international/chatfilter.xml",
            "bloque": "filtro_chat",
            "pantalla": "Chat (filtro de palabras)",
            "idioma_origen": "en",
            "texto_en": val,
            "largo_en": len(val),
            "largo_max": None,
            "caja_px": None,
            "riesgo_desborde": None,
            "notas": [f"Reemplazo actual: {v2!r}", "Opcional: adaptar lista de groserías al español"],
        })

    cadenas.extend(extraer_ltmsg(cliente))
    cadenas.extend(extraer_exe(cliente))
    cadenas.extend(extraer_servidor())

    por_origen = Counter(c["origen"] for c in cadenas)
    por_idioma = Counter(c["idioma_origen"] for c in cadenas)
    por_riesgo = Counter(c["riesgo_desborde"] for c in cadenas if c["riesgo_desborde"])

    return {
        "meta": {
            "version_esquema": 1,
            "cliente_referencia": "Data.dat MD5 30f7454d, LTMsg.dll MD5 03ab9462, EDA_limpio.exe MD5 0799387e",
            "total_cadenas": len(cadenas),
            "total_a_traducir_cliente_en": sum(
                1 for c in cadenas
                if c["origen"].startswith(("Data.dat:", "LTMsg.dll", "EDA_limpio.exe"))
                and c["idioma_origen"] == "en"
                and c["bloque"] != "filtro_chat"
            ),
            "por_origen": dict(sorted(por_origen.items())),
            "por_idioma": dict(sorted(por_idioma.items())),
            "por_riesgo_desborde": dict(sorted(por_riesgo.items())),
            "total_imagenes_ui_sin_texto_xml": len(imagenes_sin_xml),
        },
        "cadenas": cadenas,
        "imagenes_ui_strid0": imagenes_sin_xml,
    }


def cmd_generar(salida: Path, desempacado: Path, cliente: Path | None) -> int:
    inv = construir_inventario(desempacado, cliente)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    m = inv["meta"]
    print(f"Generado: {salida}")
    print(f"  Total cadenas: {m['total_cadenas']} (cliente EN a traducir: {m['total_a_traducir_cliente_en']})")
    print(f"  Por idioma: {m['por_idioma']}")
    print(f"  Por riesgo: {m['por_riesgo_desborde']}")
    for k, v in m["por_origen"].items():
        print(f"    {k:65s}: {v:4d}")
    return 0


def cmd_control(salida: Path, desempacado: Path, cliente: Path | None) -> int:
    print("== Control de extraer_textos.py ==")
    inv = construir_inventario(desempacado, cliente)
    ok = []

    def chequear(nombre: str, cond: bool, detalle: str = ""):
        print(f"  {'OK ' if cond else 'ERR'} {nombre}" + (f" — {detalle}" if detalle else ""))
        ok.append(bool(cond))

    ids = [c["id"] for c in inv["cadenas"]]
    chequear("Todos los IDs son únicos", len(ids) == len(set(ids)), f"{len(ids)} cadenas")
    by_id = {c["id"]: c for c in inv["cadenas"]}
    chequear("UI[6017] (<Jump Key>...) incluido pese a `<` sin escapar", "ui:6017" in by_id, by_id.get("ui:6017", {}).get("texto_en", ""))
    chequear("UI[4012] ('F9 Start Game') mapeado a waitroom", "ui:4012" in by_id and "waitroom" in by_id["ui:4012"]["pantalla"].lower(), by_id.get("ui:4012", {}).get("pantalla", ""))
    chequear("MapNameAndExplainString tiene los 5 bloques (250 entradas)", sum(1 for c in inv["cadenas"] if c["origen"].endswith("mapnameandexplainstring.xml")) == 250)
    chequear("Chapter1_string tiene 480 cadenas no vacías", sum(1 for c in inv["cadenas"] if c["origen"].endswith("chapter1_string.xml")) == 480)
    chequear("EDA_limpio.exe tiene 8 cadenas visibles", sum(1 for c in inv["cadenas"] if c["origen"].startswith("EDA_limpio.exe")) == 8)

    if salida.is_file():
        cargado = json.loads(salida.read_text(encoding="utf-8"))
        chequear("textos-en.json en disco coincide con la extracción actual", len(cargado["cadenas"]) == len(inv["cadenas"]), f"{len(cargado['cadenas'])} cadenas")

    todo_ok = all(ok)
    print(f"\n-> {'TODO BIEN' if todo_ok else 'ALGO FALLO'} ({sum(ok)}/{len(ok)})")
    return 0 if todo_ok else 1


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Extractor de cadenas de EDA a _trabajo/textos-en.json")
    parser.add_argument("cmd", choices=["generar", "control"])
    parser.add_argument("--cliente", type=Path, default=None, help="Carpeta con LTMsg.dll y EDA_limpio.exe")
    parser.add_argument("--desempacado", type=Path, default=None, help="Carpeta con Data.dat desempacado")
    parser.add_argument("--salida", type=Path, default=SALIDA_JSON)
    args = parser.parse_args()
    desempacado = _buscar_desempacado(args.desempacado)
    cliente = _buscar_cliente(args.cliente)
    if args.cmd == "generar":
        return cmd_generar(args.salida, desempacado, cliente)
    return cmd_control(args.salida, desempacado, cliente)


if __name__ == "__main__":
    sys.exit(main())
