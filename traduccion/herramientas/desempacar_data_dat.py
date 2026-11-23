r"""desempacar_data_dat -- lector y desempacador puro en Python de `Data.dat` (EldoS SolFS) sin abrir el juego.

Uso:
    python traduccion/herramientas/desempacar_data_dat.py control [--cliente RUTA]
    python traduccion/herramientas/desempacar_data_dat.py listar  [--cliente RUTA]
    python traduccion/herramientas/desempacar_data_dat.py extraer [--cliente RUTA] [--todo]

Cómo funciona el contenedor `Data.dat`:
  - Formato: EldoS Solid File System (SolFS), páginas de 512 bytes (0x200).
  - Cabecera de cada página: 32 bytes (8 x uint32 little-endian); cuerpo: 480 bytes (0x1E0).
  - Páginas 0, 1 y 2 (mapa de páginas, superbloque "Softnyx File System" e inodo raíz): SIN cifrar.
  - Páginas >= 3: cuerpo cifrado con AES-256-CBC:
      * contraseña: MD5(LTMsg.dll) en hex MAYÚSCULA, codificada en UTF-16-LE (64 bytes);
      * IV fijo:    HMAC-SHA256(clave = uint32_le(0x200), msg = contraseña)[:16];
      * clave pág.: HMAC-SHA256(clave = contraseña, msg = uint32_le(0x200) || uint32_le(page_id)).
  - Compresión (Tag 6 en el inodo): bloques de hasta 16 páginas (7680 B). Cada bloque comprimido lleva
    uint32_le(tam_descomprimido) + flujo zlib; si el bloque no comprime (p. ej. PNG), SolFS guarda las
    16 páginas en crudo (7680 B sin prefijo de tamaño).
  - Archivos pequeños inline: si Tag 2 mide > 8 bytes, los datos viven dentro del propio inodo (t2[8:]).
  - Nombres largos (> 22 caracteres UTF-16-LE): continúan en páginas enlazadas por ext_pno (campo +0x10).
"""
import argparse
import hashlib
import hmac
import json
import os
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[2]
CARPETA_DESEMPACADO = RAIZ_REPO / "_trabajo" / "traduccion_desempacado"

try:
    from Crypto.Cipher import AES
except ImportError:
    _deps = RAIZ_REPO / "_trabajo" / "deps16"
    if _deps.is_dir():
        sys.path.insert(0, str(_deps))
    from Crypto.Cipher import AES  # noqa: E402

PAGE_SIZE = 0x200
HDR_SIZE = 0x20
BODY_SIZE = PAGE_SIZE - HDR_SIZE  # 0x1E0 = 480 bytes
CHUNK_PAGES = 16
CHUNK_RAW_SIZE = CHUNK_PAGES * BODY_SIZE  # 7680 bytes (0x1E00)

EXTS_TEXTO_Y_UI = {
    ".xml", ".lua", ".txt", ".ini", ".cfg", ".csv", ".fnt", ".ttf", ".ttc",
}
PREFIJOS_CLAVE = (
    "string/",
    "menu/",
    "rs/",
    "console/",
    "image/ui_image/",
    "image/3d_ui_image/",
    "image/icon_image/maptitle/",
)


def buscar_cliente(cliente: Path | None = None) -> Path:
    """Encuentra la carpeta del cliente que contiene Data.dat y LTMsg.dll."""
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
        if (c / "Data.dat").is_file() and (c / "LTMsg.dll").is_file():
            return c
    raise SystemExit("⛔ No encontré Data.dat y LTMsg.dll. Indica la carpeta con --cliente RUTA")


def derivar_clave_solfs(ltmsg_bytes: bytes) -> tuple[str, bytes, bytes]:
    """Devuelve (pwd_hex_upper, pwd_utf16le, iv_16B) a partir de los bytes de LTMsg.dll."""
    pwd_str = hashlib.md5(ltmsg_bytes).hexdigest().upper()
    pwd = pwd_str.encode("utf-16-le")
    iv = hmac.new(struct.pack("<I", PAGE_SIZE), pwd, hashlib.sha256).digest()[:16]
    return pwd_str, pwd, iv


class SolFS:
    """Lector puro en Python del archivo `Data.dat` (EldoS SolFS) de EDA."""

    def __init__(self, dat_path: Path | str, ltmsg_path: Path | str | None = None,
                 ltmsg_bytes: bytes | None = None):
        self.dat_path = Path(dat_path)
        self.f = open(self.dat_path, "rb")
        self.size = self.dat_path.stat().st_size
        self.num_pages = self.size // PAGE_SIZE
        if ltmsg_bytes is None:
            if ltmsg_path is None:
                raise ValueError("Se requiere ltmsg_path o ltmsg_bytes")
            ltmsg_bytes = Path(ltmsg_path).read_bytes()
        self.pwd_str, self.pwd, self.iv = derivar_clave_solfs(ltmsg_bytes)
        self._cache: dict[int, tuple[tuple[int, ...], bytes]] = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.f and not self.f.closed:
            self.f.close()

    def read_page(self, pno: int) -> tuple[tuple[int, ...], bytes]:
        if pno in self._cache:
            return self._cache[pno]
        self.f.seek(pno * PAGE_SIZE)
        raw = self.f.read(PAGE_SIZE)
        if len(raw) < PAGE_SIZE:
            raise EOFError(f"Página {pno} truncada ({len(raw)} B)")
        hdr = struct.unpack_from("<8I", raw, 0)
        ptype, pid = hdr[0], hdr[1]
        if pno <= 2:
            body = raw[HDR_SIZE:]
        else:
            key = hmac.new(self.pwd, struct.pack("<II", PAGE_SIZE, pid), hashlib.sha256).digest()
            body = AES.new(key, AES.MODE_CBC, self.iv).decrypt(raw[HDR_SIZE:])
        res = (hdr, body)
        if ptype in (0x1F, 0x20, 0x21, 0x2B):
            self._cache[pno] = res
        return res

    def superblock_info(self) -> dict:
        self.read_page(1)
        self.f.seek(PAGE_SIZE)
        raw1 = self.f.read(PAGE_SIZE)
        magic = raw1[0:2]
        nul = raw1.find(b"\x00\x00", 0x12)
        if nul != -1 and (nul - 0x12) % 2 == 1:
            nul += 1
        label = raw1[0x12 : nul if nul != -1 else 0x80].decode("utf-16-le", errors="replace").rstrip("\x00")
        return {
            "magic": magic.decode("ascii", errors="replace"),
            "page_size": PAGE_SIZE,
            "num_pages": self.num_pages,
            "total_bytes": self.size,
            "label": label,
            "pwd_md5": self.pwd_str,
        }

    def parse_inode(self, pno: int):
        hdr, body = self.read_page(pno)
        total_len = struct.unpack_from("<I", body, 0)[0]
        file_size = struct.unpack_from("<Q", body, 0x2C)[0]
        tags: dict[int, bytes] = {}
        pos = 0x34
        end = min(total_len, len(body))
        while pos + 4 <= end:
            tag, tlen = struct.unpack_from("<HH", body, pos)
            if tlen < 4 or pos + tlen > len(body):
                break
            tags[tag] = body[pos + 4 : pos + tlen]
            pos += tlen
        return hdr, file_size, tags

    def iter_dir(self, dir_inode_pno: int):
        _, _, tags = self.parse_inode(dir_inode_pno)
        if 1 not in tags or len(tags[1]) < 8:
            return
        pno = struct.unpack_from("<I", tags[1], 4)[0]
        visited: set[int] = set()
        while pno and pno not in visited:
            visited.add(pno)
            dhdr, dbody = self.read_page(pno)
            for off in range(0, 7 * 0x40, 0x40):
                obj_id, inode_pno, flags, nchars, ext_pno = struct.unpack_from("<5I", dbody, off)
                if obj_id == 0 or inode_pno == 0 or nchars == 0 or nchars > 512:
                    continue
                inline_chars = min(nchars, 22)
                raw_name = bytearray(dbody[off + 0x14 : off + 0x14 + inline_chars * 2])
                rem = (nchars - inline_chars) * 2
                ep = ext_pno
                ext_vis: set[int] = set()
                while rem > 0 and ep and ep not in ext_vis:
                    ext_vis.add(ep)
                    eh, eb = self.read_page(ep)
                    take = min(rem, len(eb))
                    raw_name.extend(eb[:take])
                    rem -= take
                    ep = eh[4]
                name = raw_name.decode("utf-16-le", errors="replace")
                is_dir = bool(flags & 2)
                yield (name, inode_pno, is_dir, flags, obj_id)
            pno = dhdr[4]

    def walk(self, dir_inode_pno: int = 2, prefix: str = ""):
        for name, inode_pno, is_dir, flags, obj_id in self.iter_dir(dir_inode_pno):
            full = f"{prefix}/{name}" if prefix else name
            if is_dir:
                yield from self.walk(inode_pno, full)
            else:
                _, fsize, tags = self.parse_inode(inode_pno)
                yield (full, inode_pno, fsize, tags)

    def _decompress_chunk(self, cur_chunk: bytes, is_full_raw_block: bool) -> bytes:
        if is_full_raw_block and len(cur_chunk) == CHUNK_RAW_SIZE:
            ulen = struct.unpack_from("<I", cur_chunk, 0)[0]
            if 0 < ulen <= CHUNK_RAW_SIZE and cur_chunk[4:5] == b"\x78":
                try:
                    dec = zlib.decompress(cur_chunk[4:])
                    if len(dec) == ulen:
                        return dec
                except zlib.error:
                    pass
            return cur_chunk

        if len(cur_chunk) > 4:
            ulen = struct.unpack_from("<I", cur_chunk, 0)[0]
            if 0 < ulen <= CHUNK_RAW_SIZE:
                try:
                    dec = zlib.decompress(cur_chunk[4:])
                    return dec[:ulen]
                except zlib.error:
                    pass
        return cur_chunk

    def read_file(self, inode_pno: int) -> bytes:
        _, fsize, tags = self.parse_inode(inode_pno)
        if fsize == 0 or 2 not in tags:
            return b""
        t2 = tags[2]
        compressed = 6 in tags

        if len(t2) > 8:
            comp_flag = struct.unpack_from("<I", t2, 0)[0]
            payload = t2[8:]
            if comp_flag != 0 and compressed and len(payload) > 4:
                ulen = struct.unpack_from("<I", payload, 0)[0]
                try:
                    return zlib.decompress(payload[4:])[:fsize]
                except zlib.error:
                    return payload[4 : 4 + min(ulen, fsize)]
            return payload[:fsize]

        first_data_pno = struct.unpack_from("<I", t2, 4)[0]
        out = bytearray()
        cur_chunk = bytearray()
        chunk_pages = 0
        pno = first_data_pno
        visited: set[int] = set()

        def flush_chunk():
            nonlocal chunk_pages
            if not cur_chunk:
                return
            if compressed:
                out.extend(self._decompress_chunk(bytes(cur_chunk), chunk_pages == CHUNK_PAGES))
            else:
                out.extend(cur_chunk)
            cur_chunk.clear()
            chunk_pages = 0

        while pno and pno not in visited:
            visited.add(pno)
            dhdr, dbody = self.read_page(pno)
            sub_idx = dhdr[6]
            used = (dhdr[7] >> 16) & 0xFFFF
            if used == 0:
                used = BODY_SIZE
            if compressed and (sub_idx & 0xF) == 0 and cur_chunk:
                flush_chunk()
            cur_chunk.extend(dbody[:used])
            chunk_pages += 1
            pno = dhdr[4]
        flush_chunk()
        return bytes(out[:fsize])


def cmd_control(cliente: Path) -> int:
    """Comprueba el desempacador contra archivos de referencia del repo y un revés."""
    dat_path = cliente / "Data.dat"
    ltmsg_path = cliente / "LTMsg.dll"
    ok: list[bool] = []

    def chequear(nombre: str, cond: bool, detalle: str = ""):
        print(f"  {'OK ' if cond else 'ERR'} {nombre}" + (f" — {detalle}" if detalle else ""))
        ok.append(bool(cond))

    print("== Control de desempacar_data_dat.py ==")
    with SolFS(dat_path, ltmsg_path) as sfs:
        sb = sfs.superblock_info()
        chequear(
            "Superbloque SolFS leído",
            sb["magic"] == "NW" and "Softnyx" in sb["label"],
            f"label={sb['label']!r}, pwd_md5={sb['pwd_md5']}",
        )
        files = list(sfs.walk())
        by_low = {p.lower(): (p, ino, sz, tags) for p, ino, sz, tags in files}
        chequear("Catálogo completo de Data.dat", len(files) == 2063, f"{len(files)} archivos")

        for xml_name in ("Product.xml", "ItemTypeList.xml", "Skill.xml", "StageReward.xml"):
            ref_p = RAIZ_REPO / "datos" / xml_name
            _, ino_x, sz_x, _ = by_low[f"data/{xml_name.lower()}"]
            ext_x = sfs.read_file(ino_x)
            cond_x = len(ext_x) == sz_x and (
                not ref_p.is_file() or ext_x.rstrip(b"\r\n") == ref_p.read_bytes().rstrip(b"\r\n")
            )
            chequear(f"data/{xml_name} íntegro y coincide con datos/{xml_name}", cond_x, f"{len(ext_x)} B")

        _, ino_d, sz_d, _ = by_low["data/data.xml"]
        ext_d = sfs.read_file(ino_d)
        chequear("Archivo inline Tag 2 (data/data.xml)", len(ext_d) == sz_d and b"<Data>" in ext_d, f"{len(ext_d)} B")

        _, ino_png, sz_png, _ = by_low["image/icon_image/maptitle/chapter1/stage01.png"]
        ext_png = sfs.read_file(ino_png)
        chequear(
            "Bloques crudos en archivo Tag 6 (stage01.png)",
            len(ext_png) == sz_png == 38621
            and ext_png.startswith(b"\x89PNG\r\n\x1a\n")
            and ext_png.endswith(b"IEND\xaeB`\x82"),
            f"{len(ext_png)} B, cabecera PNG + IEND válidos",
        )

        largos = [p for p, _, _, _ in files if len(p.rsplit("/", 1)[-1]) > 22]
        chequear(
            "Nombres largos (>22 chars) resueltos vía ext_pno",
            len(largos) > 0 and "string/international/nameandexplainstring.xml" in by_low,
            f"{len(largos)} archivos con nombre >22 chars",
        )

    lt_malo = bytearray(ltmsg_path.read_bytes())
    lt_malo[0] ^= 0xFF
    with SolFS(dat_path, ltmsg_bytes=bytes(lt_malo)) as sfs_malo:
        try:
            encontrados = list(sfs_malo.iter_dir(2))
            hay_data = any(n.lower() == "data" for n, *_ in encontrados)
        except Exception:
            hay_data = False
        chequear("Revés: LTMsg.dll alterado (1 byte) impide descifrar Data.dat", not hay_data)

    todo_ok = all(ok)
    print(f"\n-> {'TODO BIEN' if todo_ok else 'ALGO FALLO'} ({sum(ok)}/{len(ok)})")
    return 0 if todo_ok else 1


def cmd_listar(cliente: Path, salida: Path) -> int:
    with SolFS(cliente / "Data.dat", cliente / "LTMsg.dll") as sfs:
        sb = sfs.superblock_info()
        files = list(sfs.walk())
        total_b = sum(sz for _, _, sz, _ in files)
        exts = Counter(Path(p).suffix.lower() for p, _, _, _ in files)
        dirs = Counter(p.split("/")[0].lower() for p, _, _, _ in files)
        print(f"Data.dat: {sb['label']} | {len(files)} archivos | {total_b:,} B ({total_b / 1048576:.1f} MB)")
        print("Extensiones:", exts.most_common(15))
        print("Carpetas raíz:", dirs.most_common())
        manifest = [
            {"path": p, "size": sz, "inode": ino, "compressed": 6 in tags}
            for p, ino, sz, tags in sorted(files)
        ]
        salida.mkdir(parents=True, exist_ok=True)
        out_m = salida / "manifiesto.json"
        out_m.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Manifiesto guardado en: {out_m}")
    return 0


def cmd_extraer(cliente: Path, salida: Path, todo: bool = False) -> int:
    salida.mkdir(parents=True, exist_ok=True)
    extraidos = 0
    errores = 0
    with SolFS(cliente / "Data.dat", cliente / "LTMsg.dll") as sfs:
        files = list(sfs.walk())
        for p, ino, sz, tags in sorted(files):
            pl = p.lower()
            ext = Path(p).suffix.lower()
            if not todo and not (ext in EXTS_TEXTO_Y_UI or pl.startswith(PREFIJOS_CLAVE)):
                continue
            data = sfs.read_file(ino)
            if len(data) != sz:
                print(f"  WARN tamaño distinto en {p}: esperado {sz}, leído {len(data)}")
                errores += 1
            dst = salida / Path(*p.split("/"))
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            extraidos += 1
        manifest = [
            {"path": p, "size": sz, "inode": ino, "compressed": 6 in tags}
            for p, ino, sz, tags in sorted(files)
        ]
        (salida / "manifiesto.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(f"Extraídos {extraidos} archivos en {salida} (errores de tamaño: {errores})")
    return 0 if errores == 0 else 1


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Desempacador SolFS para Data.dat de EDA")
    parser.add_argument("--cliente", type=Path, default=None, help="Carpeta con Data.dat y LTMsg.dll")
    parser.add_argument("--salida", type=Path, default=CARPETA_DESEMPACADO, help="Carpeta de salida (por defecto _trabajo/traduccion_desempacado)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("control", help="Verifica integridad y compara con los XML de datos/")
    sub.add_parser("listar", help="Lista resumen y escribe manifiesto.json")
    p_ext = sub.add_parser("extraer", help="Extrae archivos a _trabajo/traduccion_desempacado/")
    p_ext.add_argument("--todo", action="store_true", help="Extrae los 2063 archivos completos (~697 MB)")
    args = parser.parse_args()
    cliente = buscar_cliente(args.cliente)
    if args.cmd == "control":
        return cmd_control(cliente)
    if args.cmd == "listar":
        return cmd_listar(cliente, args.salida)
    if args.cmd == "extraer":
        return cmd_extraer(cliente, args.salida, todo=args.todo)
    return 1


if __name__ == "__main__":
    sys.exit(main())
