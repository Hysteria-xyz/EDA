/* eda_traduccion.c — ★ (23-nov) TRADUCCIÓN EN MEMORIA (embebida + carpeta suelta `traducciones\<idioma>\`).
 *
 * Qué hace: permite traducir los textos XML, texturas HGE (.tga/.png/.bmp), scripts Lua y texturas 3D (.dtx)
 * de EDA SIN tocar un solo byte de `EDA_limpio.exe`, `Data.dat` ni `LTMsg.dll` (cuyo MD5 es la clave AES-256
 * de `Data.dat`). Respeta todas las reglas de `documentacion/POR_QUE_LA_DLL.md`.
 *
 * Punto común verificado en `EDA_limpio.exe` (0799387e, PE sello 0x4A858317, imagen 0x5DB000):
 *   Toda lectura de `Data.dat` en el juego — tanto la capa VFS de XML/HGE/Lua (vtable 0x8B2520: `0x7A9120` y
 *   `0x7A82A0..0x7A8354`, usada por `0x7ADF20` XML, `0x7857C0` texturas HGE, `0x7804D0`, `0x7843F0`, `0x784A10`)
 *   como el motor 3D LithTech (`0x731E37`, `0x72FE80..0x72FF94`, `0x7320DD`, `0x7321A3`, `0x7321C6`) — pasa por
 *   exactamente las mismas funciones __stdcall de EldoS SolFS:
 *     · 0x7FA410 SolFSOpenFile    (9 args, ret 0x24) — 2 sitios: 0x731E37, 0x7A9236
 *     · 0x7FA460 SolFSCloseFile   (1 arg,  ret 0x04) — 4 sitios: 0x7320DD, 0x7321C6, 0x7A93C4, 0x7A94C7
 *     · 0x7FA570 SolFSGetFileSize (2 args, ret 0x08) — 3 sitios: 0x72FED6, 0x7321A3, 0x7A82E9
 *     · 0x7FA730 SolFSSeek        (4 args, ret 0x10) — 3 sitios: 0x72FF1A, 0x7A82BF, 0x7A8319
 *     · 0x7FA7B0 SolFSGetFilePos  (2 args, ret 0x08) — 1 sitio:  0x72FE96
 *     · 0x7FA800 SolFSReadFile    (4 args, ret 0x10) — 2 sitios: 0x72FF4C, 0x7A8354
 *     · 0x7FA260 SolFSGetInfo     (2 args, ret 0x08) — 1 sitio:  0x72FF94 (el otro usa el handle del archivo contenedor)
 *
 * Cómo funciona:
 *   1. `[traduccion] idioma=es` en `eda_d3d9.ini` (o `EDA_IDIOMA`). Prendido en español por defecto; `idioma=en`,
 *      `off`, `ninguno`, vacío o `[general] mejoras=0` lo apagan sin enganchar nada.
 *   2. Verifica el PE del exe, los 7 prólogos de SolFS y las 16 llamadas `E8 rel32` ANTES de tocar un solo byte.
 *      Si uno solo no coincide (otro exe), no engancha nada y lo anota en `eda_d3d9.log`.
 *   3. Cuando el juego abre un archivo de `Data.dat` para lectura, normaliza la ruta y busca en orden:
 *      (1) archivo suelto `<carpeta_exe>\traducciones\<idioma>\<ruta>` (para probar cambios sin recompilar);
 *      (2) archivo embebido en la DLL (`eda_traduccion_datos.h`, generado desde `traduccion/<idioma>/`);
 *      (3) `Data.dat` original.
 *      Tanto los archivos sueltos como los embebidos devuelven un puntero a un casillero propio `g_tr_slots[i]`
 *      (imposible de confundir con un puntero del heap de SolFS).
 *   4. Opcional (prendido con `idioma=es`, `[traduccion] cadenas_exe=0` lo apaga): parcha en memoria 3 literales
 *      UTF-16-LE del mismo largo exacto en `.rdata` (`LV%3d` → `Nv%3d`, `%dGold` → `%d Oro`,
 *      `[%s]%s(%dGold)` → `[%s]%s(%d Oro)`), verificando los bytes originales primero.
 */

#ifndef EDA_TRADUCCION_SOLO_LOGICA
#define EDA_TRADUCCION_SOLO_LOGICA 0
#endif

#include <stddef.h>
#include <string.h>
#include "eda_traduccion_datos.h"

/* El EDA_limpio.exe conocido (md5 0799387e...): su PE */
#define TR_EXE_BASE   0x00400000u
#define TR_EXE_SELLO  0x4A858317u
#define TR_EXE_TAMANO 0x005DB000u

/* Las 7 funciones SolFS que operan sobre handles de archivo abiertos */
#define TR_FN_OPEN  0x007FA410u
#define TR_FN_CLOSE 0x007FA460u
#define TR_FN_SIZE  0x007FA570u
#define TR_FN_SEEK  0x007FA730u
#define TR_FN_POS   0x007FA7B0u
#define TR_FN_READ  0x007FA800u
#define TR_FN_INFO  0x007FA260u

/* Diagnóstico de glifos FreeType (23-nov: investigar la «ñ» deformada): hgeFTFont::CreateGlyph y FT_Load_Glyph */
#define TR_SITIO_CREATE_GLYPH 0x00771FF1u
#define TR_FN_CREATE_GLYPH    0x00770A00u
#define TR_FN_FT_LOAD_GLYPH   0x0081DD30u

static const unsigned char TR_PROLOGO_CREATE_GLYPH[8] = {0x83, 0xEC, 0x08, 0x55, 0x56, 0x8B, 0xE9, 0x6A};
static const unsigned char TR_PROLOGO_FT_LOAD[8]      = {0x55, 0x8B, 0x6C, 0x24, 0x08, 0x85, 0xED, 0x56};

enum {
    TR_OP_OPEN = 0,
    TR_OP_CLOSE,
    TR_OP_SIZE,
    TR_OP_SEEK,
    TR_OP_POS,
    TR_OP_READ,
    TR_OP_INFO
};

typedef struct {
    unsigned long fn;
    unsigned char bytes[8];
    const char *nombre;
} TR_PROLOGO;

static const TR_PROLOGO TR_PROLOGOS[] = {
    {TR_FN_OPEN,  {0x8B, 0x44, 0x24, 0x04, 0x85, 0xC0, 0x75, 0x08}, "SolFSOpenFile"},
    {TR_FN_CLOSE, {0x56, 0x8B, 0x74, 0x24, 0x08, 0x85, 0xF6, 0x75}, "SolFSCloseFile"},
    {TR_FN_SIZE,  {0x83, 0xEC, 0x08, 0x8B, 0x44, 0x24, 0x0C, 0x33}, "SolFSGetFileSize"},
    {TR_FN_SEEK,  {0x83, 0xEC, 0x08, 0x8B, 0x4C, 0x24, 0x0C, 0x33}, "SolFSSeek"},
    {TR_FN_POS,   {0x8B, 0x44, 0x24, 0x04, 0x85, 0xC0, 0x75, 0x08}, "SolFSGetFilePos"},
    {TR_FN_READ,  {0x8B, 0x44, 0x24, 0x04, 0x85, 0xC0, 0x75, 0x08}, "SolFSReadFile"},
    {TR_FN_INFO,  {0x8B, 0x44, 0x24, 0x04, 0x85, 0xC0, 0x75, 0x08}, "SolFSGetInfo"},
};
#define TR_NPROLOGOS ((int)(sizeof(TR_PROLOGOS) / sizeof(TR_PROLOGOS[0])))

typedef struct {
    unsigned long sitio;
    unsigned long destino;
    int op;
    const char *quien;
} TR_SITIO;

static const TR_SITIO TR_SITIOS[] = {
    /* Open (2): LithTech 3D + VFS XML/HGE/Lua */
    {0x00731E37u, TR_FN_OPEN,  TR_OP_OPEN,  "LithTech Open"},
    {0x007A9236u, TR_FN_OPEN,  TR_OP_OPEN,  "VFS Open"},
    /* Close (4) */
    {0x007320DDu, TR_FN_CLOSE, TR_OP_CLOSE, "LithTech Close 1"},
    {0x007321C6u, TR_FN_CLOSE, TR_OP_CLOSE, "LithTech Close 2"},
    {0x007A93C4u, TR_FN_CLOSE, TR_OP_CLOSE, "VFS Close"},
    {0x007A94C7u, TR_FN_CLOSE, TR_OP_CLOSE, "VFS Dtor Close"},
    /* GetFileSize (3) */
    {0x0072FED6u, TR_FN_SIZE,  TR_OP_SIZE,  "LithTech Size 1"},
    {0x007321A3u, TR_FN_SIZE,  TR_OP_SIZE,  "LithTech Size 2"},
    {0x007A82E9u, TR_FN_SIZE,  TR_OP_SIZE,  "VFS Size"},
    /* Seek (3) */
    {0x0072FF1Au, TR_FN_SEEK,  TR_OP_SEEK,  "LithTech Seek"},
    {0x007A82BFu, TR_FN_SEEK,  TR_OP_SEEK,  "VFS Seek 1"},
    {0x007A8319u, TR_FN_SEEK,  TR_OP_SEEK,  "VFS Seek 2"},
    /* GetFilePos (1) */
    {0x0072FE96u, TR_FN_POS,   TR_OP_POS,   "LithTech Pos"},
    /* ReadFile (2) */
    {0x0072FF4Cu, TR_FN_READ,  TR_OP_READ,  "LithTech Read"},
    {0x007A8354u, TR_FN_READ,  TR_OP_READ,  "VFS Read"},
    /* GetInfo sobre handle de archivo (1) */
    {0x0072FF94u, TR_FN_INFO,  TR_OP_INFO,  "LithTech Info"},
};
#define TR_NSITIOS ((int)(sizeof(TR_SITIOS) / sizeof(TR_SITIOS[0])))

/* Literales UTF-16-LE en .rdata del mismo largo exacto (sólo para idioma=es) */
typedef struct {
    unsigned long va;
    const char *orig;
    const char *nuevo;
} TR_CADENA_ES;

static const TR_CADENA_ES TR_CADENAS_ES[] = {
    {0x00899700u, "LV%3d",          "Nv%3d"},
    {0x00899F94u, "%dGold",         "%d Oro"},
    {0x00899FB4u, "[%s]%s(%dGold)", "[%s]%s(%d Oro)"},
};
#define TR_NCADENAS ((int)(sizeof(TR_CADENAS_ES) / sizeof(TR_CADENAS_ES[0])))

/* ── lógica pura (compilable y verificable en Linux y Windows sin el juego) ─────────────────────────────── */

static int tr_ascii_lower(int c)
{
    return (c >= 'A' && c <= 'Z') ? (c + ('a' - 'A')) : c;
}

/* Decide si la traducción debe activarse. Apagada si mejoras==0, vacío, "en", "0", "off", "ninguno" o inválido. */
static int tr_idioma_activo(const char *cfg, int mejoras, char out[16])
{
    if (out) out[0] = 0;
    if (!mejoras || !cfg) return 0;
    while (*cfg == ' ' || *cfg == '\t' || *cfg == '\r' || *cfg == '\n') cfg++;
    int n = 0;
    char tmp[16];
    while (*cfg && *cfg != ' ' && *cfg != '\t' && *cfg != '\r' && *cfg != '\n') {
        int c = tr_ascii_lower((unsigned char)*cfg++);
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_')) return 0;
        if (n >= 15) return 0;
        tmp[n++] = (char)c;
    }
    while (*cfg == ' ' || *cfg == '\t' || *cfg == '\r' || *cfg == '\n') cfg++;
    if (*cfg != 0) return 0;
    tmp[n] = 0;
    if (n < 2) return 0;
    if ((tmp[0] == 'e' && tmp[1] == 'n' && tmp[2] == 0)
        || (tmp[0] == 'o' && tmp[1] == 'f' && tmp[2] == 'f' && tmp[3] == 0)
        || (tmp[0] == 'n' && tmp[1] == 'o' && tmp[2] == 0)
        || (tmp[0] == 'n' && tmp[1] == 'i' && tmp[2] == 'n' && tmp[3] == 'g'
            && tmp[4] == 'u' && tmp[5] == 'n' && tmp[6] == 'o' && tmp[7] == 0))
        return 0;
    if (out) {
        for (int i = 0; i <= n; i++) out[i] = tmp[i];
    }
    return 1;
}

/* Normaliza una ruta interna de Data.dat (UTF-16) a minúsculas con '\', sin prefijos ./ ni / ni traversal (..). */
static int tr_normalizar_ruta(const unsigned short *in, unsigned short *out, int cap)
{
    if (!in || !out || cap < 2) return 0;
    int i = 0;
    /* quitar prefijos "/", "\", "./", ".\" repetidos */
    for (;;) {
        if (in[i] == '/' || in[i] == '\\') { i++; continue; }
        if (in[i] == '.' && (in[i + 1] == '/' || in[i + 1] == '\\')) { i += 2; continue; }
        break;
    }
    int o = 0, seg_len = 0, seg_puntos = 0;
    for (; in[i]; i++) {
        unsigned short c = in[i];
        if (c < 0x20 || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|')
            return 0;
        if (c == '/' || c == '\\') {
            if (seg_len == 0) continue;                     /* colapsar // o \\ */
            if (seg_len == seg_puntos && (seg_len == 1 || seg_len == 2)) return 0;   /* "." o ".." */
            if (o + 1 >= cap) return 0;
            out[o++] = '\\';
            seg_len = 0;
            seg_puntos = 0;
            continue;
        }
        if (c >= 'A' && c <= 'Z') c = (unsigned short)(c + ('a' - 'A'));
        if (o + 1 >= cap) return 0;
        out[o++] = c;
        seg_len++;
        if (c == '.') seg_puntos++;
    }
    if (seg_len > 0 && seg_len == seg_puntos && (seg_len == 1 || seg_len == 2)) return 0;
    while (o > 0 && out[o - 1] == '\\') o--;
    if (o == 0) return 0;
    out[o] = 0;
    return 1;
}

/* Arma `<base_dir>traducciones\<idioma>\<ruta_normalizada>` en UTF-16. Devuelve 1 si OK, 0 si inválida o desborda. */
static int tr_armar_ruta(const unsigned short *base_dir, const char *idioma,
                         const unsigned short *solfs_path, unsigned short *out, int cap)
{
    unsigned short rel[260];
    if (!base_dir || !idioma || !idioma[0] || !out || cap < 32) return 0;
    if (!tr_normalizar_ruta(solfs_path, rel, 260)) return 0;
    int o = 0;
    for (int i = 0; base_dir[i]; i++) {
        if (o + 1 >= cap) return 0;
        out[o++] = base_dir[i];
    }
    if (o > 0 && out[o - 1] != '\\' && out[o - 1] != '/') {
        if (o + 1 >= cap) return 0;
        out[o++] = '\\';
    }
    static const char pref[] = "traducciones\\";
    for (int i = 0; pref[i]; i++) {
        if (o + 1 >= cap) return 0;
        out[o++] = (unsigned short)(unsigned char)pref[i];
    }
    for (int i = 0; idioma[i]; i++) {
        if (o + 1 >= cap) return 0;
        out[o++] = (unsigned short)(unsigned char)idioma[i];
    }
    if (o + 1 >= cap) return 0;
    out[o++] = '\\';
    for (int i = 0; rel[i]; i++) {
        if (o + 1 >= cap) return 0;
        out[o++] = rel[i];
    }
    out[o] = 0;
    return 1;
}

/* ¿En `p` está exactamente `call rel32` (E8) desde `sitio` hacia `destino`? */
static int tr_es_llamada(const unsigned char *p, unsigned long sitio, unsigned long destino)
{
    unsigned long rel = (destino - (sitio + 5u)) & 0xFFFFFFFFu;
    return p[0] == 0xE8
           && p[1] == (rel & 0xFFu)
           && p[2] == ((rel >> 8) & 0xFFu)
           && p[3] == ((rel >> 16) & 0xFFu)
           && p[4] == ((rel >> 24) & 0xFFu);
}

/* ¿En `p` está exactamente `ascii` en UTF-16-LE con su terminador NUL (00 00)? */
static int tr_coincide_utf16(const unsigned char *p, const char *ascii)
{
    size_t i = 0;
    for (; ascii[i]; i++) {
        if (p[2 * i] != (unsigned char)ascii[i] || p[2 * i + 1] != 0) return 0;
    }
    return p[2 * i] == 0 && p[2 * i + 1] == 0;
}

/* Escribe `ascii` en UTF-16-LE (incluye el terminador NUL; sólo llamar cuando orig y nuevo tienen el mismo largo). */
static void tr_escribir_utf16(unsigned char *p, const char *ascii)
{
    size_t i = 0;
    for (; ascii[i]; i++) {
        p[2 * i] = (unsigned char)ascii[i];
        p[2 * i + 1] = 0;
    }
    p[2 * i] = 0;
    p[2 * i + 1] = 0;
}

/* ¿Este carácter entra en el diagnóstico de glifos (ñ, Ñ, ó, n, ü)? */
static int tr_es_glifo_diag(unsigned short ch)
{
    return ch == 0x00F1u || ch == 0x00D1u || ch == 0x00F3u || ch == 0x006Eu || ch == 0x00FCu;
}

static const char *tr_nombre_glifo_diag(unsigned short ch)
{
    switch (ch) {
    case 0x00F1u: return "ñ";
    case 0x00D1u: return "Ñ";
    case 0x00F3u: return "ó";
    case 0x006Eu: return "n";
    case 0x00FCu: return "ü";
    default:      return "?";
    }
}

/* Cuántos archivos embebidos existen en la DLL para `idioma`. */
static int tr_contar_embebidos(const char *idioma)
{
    if (!idioma || !idioma[0]) return 0;
    int n = 0;
    for (int i = 0; i < TR_NEMBEBIDOS; i++) {
        if (TR_EMBEBIDOS[i].idioma && strcmp(TR_EMBEBIDOS[i].idioma, idioma) == 0) n++;
    }
    return n;
}

/* Busca `ruta_norm` (salida de tr_normalizar_ruta, minúsculas con '\') en los archivos embebidos de `idioma`. */
static const TR_EMBEBIDO *tr_buscar_embebido(const char *idioma, const unsigned short *ruta_norm)
{
    if (!idioma || !idioma[0] || !ruta_norm || !ruta_norm[0]) return NULL;
    for (int i = 0; i < TR_NEMBEBIDOS; i++) {
        const TR_EMBEBIDO *e = &TR_EMBEBIDOS[i];
        if (!e->idioma || !e->ruta || strcmp(e->idioma, idioma) != 0) continue;
        size_t j = 0;
        for (; e->ruta[j] && ruta_norm[j]; j++) {
            if ((unsigned short)(unsigned char)e->ruta[j] != ruta_norm[j]) break;
        }
        if (e->ruta[j] == 0 && ruta_norm[j] == 0) return e;
    }
    return NULL;
}

/* Seek en memoria (FILE_BEGIN=0, FILE_CURRENT=1, FILE_END=2) equivalente a SolFSSeek / SetFilePointer. */
static int tr_mem_seek(unsigned long tam, unsigned long *pos_io, long offset, unsigned long metodo,
                       unsigned long *out_pos)
{
    if (!pos_io) return -1;
    if (metodo > 2u) return -24;
    long long base = (metodo == 0u) ? 0LL : ((metodo == 1u) ? (long long)(*pos_io) : (long long)tam);
    long long nuevo = base + (long long)offset;
    if (nuevo < 0LL) return -1;
    *pos_io = (unsigned long)nuevo;
    if (out_pos) *out_pos = *pos_io;
    return 0;
}

/* Lectura en memoria equivalente a SolFSReadFile / ReadFile. */
static int tr_mem_read(const unsigned char *datos, unsigned long tam, unsigned long *pos_io,
                       void *buf, unsigned long pedir, unsigned long *out_leidos)
{
    if (!pos_io) return -1;
    if (!datos || *pos_io >= tam || pedir == 0u) {
        if (out_leidos) *out_leidos = 0u;
        return 0;
    }
    unsigned long disp = tam - *pos_io;
    unsigned long n = pedir < disp ? pedir : disp;
    if (buf && n) memcpy(buf, datos + *pos_io, (size_t)n);
    *pos_io += n;
    if (out_leidos) *out_leidos = n;
    return 0;
}

#if !EDA_TRADUCCION_SOLO_LOGICA

/* ── parte Windows (integrada en d3d9.dll) ────────────────────────────────────────────────────────────── */

typedef int (WINAPI *TR_SOLFS_OPEN)(DWORD, const WCHAR *, DWORD, DWORD, DWORD, DWORD, const void *, DWORD, DWORD *);
typedef int (WINAPI *TR_SOLFS_CLOSE)(DWORD);
typedef int (WINAPI *TR_SOLFS_SIZE)(DWORD, DWORD *);
typedef int (WINAPI *TR_SOLFS_SEEK)(DWORD, LONG, DWORD, DWORD *);
typedef int (WINAPI *TR_SOLFS_POS)(DWORD, DWORD *);
typedef int (WINAPI *TR_SOLFS_READ)(DWORD, void *, DWORD, DWORD *);
typedef int (WINAPI *TR_SOLFS_INFO)(DWORD, void *);

#define TR_MAX_SLOTS 64
typedef struct {
    HANDLE fh;                     /* != INVALID_HANDLE_VALUE si viene del disco (carpeta suelta) */
    const unsigned char *mem;      /* != NULL si viene embebido en la DLL */
    unsigned long mem_tam;
    unsigned long mem_pos;
    volatile LONG en_uso;
} TR_SLOT;

static char g_tr_idioma_cfg[32];
static char g_tr_idioma[16];
static int g_tr_cadenas_exe = 1;
static int g_tr_diag_glifos = 0;
static int g_tr_carpeta_suelta;
static int g_tr_instalado;
static int g_tr_diag_instalado;
static volatile LONG g_tr_diag_n;
static LONG g_tr_diag_cmp_enie;
static LONG g_tr_diag_cmp_oac;
static WCHAR g_tr_base_w[MAX_PATH];
static TR_SLOT g_tr_slots[TR_MAX_SLOTS];
static CRITICAL_SECTION g_tr_cs;
static int g_tr_cursor;
static volatile LONG g_tr_redirigidos;
static volatile LONG g_tr_redirigidos_sueltos;
static volatile LONG g_tr_redirigidos_emb;
/* ★ (24-nov, EXPERIMENTAL, [pvp] batalla=1; APAGADO por defecto) la capa PvP: <carpeta_exe>\pvp\<ruta>, antes que la
 *   traducción. La sala con equipos (menu\international\waitroom_mission.xml) se sirve SÓLO mientras el server dice
 *   que la sala es de duelo (g_tr_pvp_sala, por el chat «[PVP]», eda_d3d9.c); medido: el juego relee ese XML en
 *   cada entrada a una sala. Lo demás de pvp\ (las barras roja / azul) siempre: sólo se usa si el XML lo pide. */
static int g_tr_pvp_capa;
static volatile LONG g_tr_pvp_sala;

static int tr_es_ruta(const unsigned short *rel, const char *ascii)
{
    int i = 0;
    for (; rel[i] && ascii[i]; i++)
        if (rel[i] != (unsigned char)ascii[i]) return 0;
    return !rel[i] && !ascii[i];
}

static int tr_abrir_pvp(const unsigned short *rel, DWORD *out_handle);

static void tr_leer_ini(HMODULE self, const char *ini)
{
    g_tr_pvp_capa = GetPrivateProfileIntA("pvp", "batalla", 0, ini);
    g_tr_idioma_cfg[0] = 0;
    g_tr_idioma[0] = 0;
    g_tr_base_w[0] = 0;
    if (GetModuleFileNameW(self, g_tr_base_w, MAX_PATH)) {
        WCHAR *b = wcsrchr(g_tr_base_w, L'\\');
        if (b) b[1] = 0;
        else g_tr_base_w[0] = 0;
    }
    /* Por defecto "es" si la clave no existe en un .ini previo del jugador; idioma=en / off / vacío la apaga */
    GetPrivateProfileStringA("traduccion", "idioma", "es", g_tr_idioma_cfg, sizeof(g_tr_idioma_cfg), ini);
    g_tr_cadenas_exe = GetPrivateProfileIntA("traduccion", "cadenas_exe", 1, ini);
    g_tr_diag_glifos = GetPrivateProfileIntA("traduccion", "diag_glifos", 0, ini);
    char env[32];
    DWORD n = GetEnvironmentVariableA("EDA_IDIOMA", env, sizeof(env));
    if (n && n < sizeof(env)) lstrcpynA(g_tr_idioma_cfg, env, (int)sizeof(g_tr_idioma_cfg));
    if (GetEnvironmentVariableA("EDA_DIAG_GLIFOS", env, sizeof(env))) g_tr_diag_glifos = atoi(env);
}

static TR_SLOT *tr_slot_de(DWORD handle)
{
    ULONG_PTR base = (ULONG_PTR)&g_tr_slots[0];
    ULONG_PTR fin = (ULONG_PTR)&g_tr_slots[TR_MAX_SLOTS];
    ULONG_PTR h = (ULONG_PTR)handle;
    if (h < base || h >= fin) return NULL;
    if (((h - base) % sizeof(TR_SLOT)) != 0) return NULL;
    TR_SLOT *s = (TR_SLOT *)h;
    return s->en_uso ? s : NULL;
}

static TR_SLOT *tr_slot_tomar(HANDLE fh, const TR_EMBEBIDO *emb)
{
    TR_SLOT *elegido = NULL;
    EnterCriticalSection(&g_tr_cs);
    for (int i = 0; i < TR_MAX_SLOTS; i++) {
        int idx = (g_tr_cursor + i) % TR_MAX_SLOTS;
        if (!g_tr_slots[idx].en_uso) {
            g_tr_slots[idx].fh = fh;
            g_tr_slots[idx].mem = emb ? emb->datos : NULL;
            g_tr_slots[idx].mem_tam = emb ? emb->tam : 0u;
            g_tr_slots[idx].mem_pos = 0u;
            g_tr_slots[idx].en_uso = 1;
            g_tr_cursor = (idx + 1) % TR_MAX_SLOTS;
            elegido = &g_tr_slots[idx];
            break;
        }
    }
    LeaveCriticalSection(&g_tr_cs);
    return elegido;
}

static void tr_anotar_redirigido(const unsigned short *rel, const char *fuente)
{
    LONG n = InterlockedIncrement(&g_tr_redirigidos);
    if (n <= 16) {
        char utf8[260];
        utf8[0] = 0;
        WideCharToMultiByte(CP_UTF8, 0, (const WCHAR *)rel, -1, utf8, sizeof(utf8), NULL, NULL);
        apuntar("  [traduccion] #%ld (%s) → %s", (long)n, fuente, utf8[0] ? utf8 : "?");
    } else if (n == 17) {
        apuntar("  [traduccion] (siguen archivos redirigidos; el total queda al cerrar)");
    }
}

static int tr_abrir_pvp(const unsigned short *rel, DWORD *out_handle)
{
    if (!g_tr_base_w[0]) return 0;
    if (tr_es_ruta(rel, "menu\\international\\waitroom_mission.xml")) {
        apuntar("  [pvp] sala: %s", g_tr_pvp_sala ? "de DUELO → la sala con equipos (pvp\\)" : "normal → la de siempre");
        if (!g_tr_pvp_sala) return 0;
    }
    /* ★ (24-nov) los guiones de escenario de pvp\ (la ARENA: data\scenario\…) también sólo en una sala de duelo: en
     *   cualquier otra sala la stage es la original. (El guion se lee al cargar la stage, después del aviso de la sala.) */
    const char *esc = "data\\scenario\\";
    int k = 0;
    while (esc[k] && rel[k] == (unsigned char)esc[k]) k++;
    if (!esc[k] && !g_tr_pvp_sala) return 0;
    WCHAR completa[MAX_PATH];
    int nb = lstrlenW(g_tr_base_w), nr = 0;
    while (rel[nr]) nr++;
    if (nb + 4 + nr >= MAX_PATH) return 0;
    lstrcpyW(completa, g_tr_base_w);
    lstrcatW(completa, L"pvp\\");
    for (int i = 0; i <= nr; i++) completa[nb + 4 + i] = (WCHAR)rel[i];
    DWORD attr = GetFileAttributesW(completa);
    if (attr == INVALID_FILE_ATTRIBUTES || (attr & FILE_ATTRIBUTE_DIRECTORY)) return 0;
    HANDLE fh = CreateFileW(completa, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (fh == INVALID_HANDLE_VALUE) return 0;
    TR_SLOT *s = tr_slot_tomar(fh, NULL);
    if (!s) { CloseHandle(fh); return 0; }
    *out_handle = (DWORD)(ULONG_PTR)s;
    InterlockedIncrement(&g_tr_redirigidos_sueltos);
    tr_anotar_redirigido(rel, g_tr_pvp_sala ? "pvp, sala de duelo" : "pvp");
    if (!esc[k]) apuntar("  [pvp] stage de la sala de DUELO: el guion de la arena (pvp\\)");
    return 1;
}

static int WINAPI tr_mi_open(DWORD storage, const WCHAR *nombre, DWORD b_leer, DWORD b_escribir,
                             DWORD comp_leer, DWORD comp_escr, const void *clave, DWORD clave_len, DWORD *out_handle)
{
    if (nombre && out_handle && b_leer && g_tr_idioma[0]) {
        unsigned short rel[260];
        if (tr_normalizar_ruta((const unsigned short *)nombre, rel, 260)) {
            /* 0. ★ la capa PvP (experimental, apagada por defecto): ver g_tr_pvp_capa */
            if (g_tr_pvp_capa && tr_abrir_pvp(rel, out_handle)) return 0;
            /* 1. Prioridad: archivo suelto en traducciones\<idioma>\<ruta> (para probar cambios sin recompilar) */
            if (g_tr_carpeta_suelta && g_tr_base_w[0]) {
                unsigned short completa[MAX_PATH];
                if (tr_armar_ruta((const unsigned short *)g_tr_base_w, g_tr_idioma,
                                  (const unsigned short *)nombre, completa, MAX_PATH)) {
                    DWORD attr = GetFileAttributesW((const WCHAR *)completa);
                    if (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY)) {
                        HANDLE fh = CreateFileW((const WCHAR *)completa, GENERIC_READ, FILE_SHARE_READ,
                                                NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
                        if (fh != INVALID_HANDLE_VALUE) {
                            TR_SLOT *s = tr_slot_tomar(fh, NULL);
                            if (s) {
                                *out_handle = (DWORD)(ULONG_PTR)s;
                                InterlockedIncrement(&g_tr_redirigidos_sueltos);
                                tr_anotar_redirigido(rel, "suelto");
                                return 0;
                            }
                            CloseHandle(fh);
                        }
                    }
                }
            }
            /* 2. Si no está suelto, buscar embebido en la DLL */
            const TR_EMBEBIDO *emb = tr_buscar_embebido(g_tr_idioma, rel);
            if (emb) {
                TR_SLOT *s = tr_slot_tomar(INVALID_HANDLE_VALUE, emb);
                if (s) {
                    *out_handle = (DWORD)(ULONG_PTR)s;
                    InterlockedIncrement(&g_tr_redirigidos_emb);
                    tr_anotar_redirigido(rel, "embebido");
                    return 0;
                }
            }
        }
    }
    /* 3. Si no está ni suelto ni embebido, sigue a Data.dat como siempre */
    return ((TR_SOLFS_OPEN)(ULONG_PTR)TR_FN_OPEN)(storage, nombre, b_leer, b_escribir,
                                                  comp_leer, comp_escr, clave, clave_len, out_handle);
}

static int WINAPI tr_mi_close(DWORD handle)
{
    TR_SLOT *s = tr_slot_de(handle);
    if (s) {
        HANDLE fh = INVALID_HANDLE_VALUE;
        EnterCriticalSection(&g_tr_cs);
        if (s->en_uso) {
            fh = s->fh;
            s->fh = INVALID_HANDLE_VALUE;
            s->mem = NULL;
            s->mem_tam = 0u;
            s->mem_pos = 0u;
            s->en_uso = 0;
        }
        LeaveCriticalSection(&g_tr_cs);
        if (fh != INVALID_HANDLE_VALUE) CloseHandle(fh);
        return 0;
    }
    return ((TR_SOLFS_CLOSE)(ULONG_PTR)TR_FN_CLOSE)(handle);
}

static int WINAPI tr_mi_size(DWORD handle, DWORD *out_size)
{
    TR_SLOT *s = tr_slot_de(handle);
    if (s) {
        if (s->mem) {
            if (out_size) *out_size = (DWORD)s->mem_tam;
            return 0;
        }
        DWORD sz = GetFileSize(s->fh, NULL);
        if (sz == INVALID_FILE_SIZE && GetLastError() != NO_ERROR) return -1;
        if (out_size) *out_size = sz;
        return 0;
    }
    return ((TR_SOLFS_SIZE)(ULONG_PTR)TR_FN_SIZE)(handle, out_size);
}

static int WINAPI tr_mi_seek(DWORD handle, LONG pos, DWORD origen, DWORD *out_pos)
{
    TR_SLOT *s = tr_slot_de(handle);
    if (s) {
        DWORD metodo = origen & 0xFFFFu;
        if (s->mem) {
            unsigned long np = 0u;
            int rc = tr_mem_seek(s->mem_tam, &s->mem_pos, (long)pos, (unsigned long)metodo, &np);
            if (rc == 0 && out_pos) *out_pos = (DWORD)np;
            return rc;
        }
        if (metodo > 2u) return -24; /* FILE_BEGIN=0, FILE_CURRENT=1, FILE_END=2 */
        DWORD np = SetFilePointer(s->fh, pos, NULL, metodo);
        if (np == INVALID_SET_FILE_POINTER && GetLastError() != NO_ERROR) return -1;
        if (out_pos) *out_pos = np;
        return 0;
    }
    return ((TR_SOLFS_SEEK)(ULONG_PTR)TR_FN_SEEK)(handle, pos, origen, out_pos);
}

static int WINAPI tr_mi_pos(DWORD handle, DWORD *out_pos)
{
    TR_SLOT *s = tr_slot_de(handle);
    if (s) {
        if (s->mem) {
            if (out_pos) *out_pos = (DWORD)s->mem_pos;
            return 0;
        }
        DWORD np = SetFilePointer(s->fh, 0, NULL, FILE_CURRENT);
        if (np == INVALID_SET_FILE_POINTER && GetLastError() != NO_ERROR) return -1;
        if (out_pos) *out_pos = np;
        return 0;
    }
    return ((TR_SOLFS_POS)(ULONG_PTR)TR_FN_POS)(handle, out_pos);
}

static int WINAPI tr_mi_read(DWORD handle, void *buf, DWORD tam, DWORD *out_leidos)
{
    TR_SLOT *s = tr_slot_de(handle);
    if (s) {
        if (s->mem) {
            unsigned long leidos = 0u;
            int rc = tr_mem_read(s->mem, s->mem_tam, &s->mem_pos, buf, (unsigned long)tam, &leidos);
            if (out_leidos) *out_leidos = (DWORD)leidos;
            return rc;
        }
        DWORD leidos = 0;
        if (!ReadFile(s->fh, buf, tam, &leidos, NULL)) {
            if (out_leidos) *out_leidos = 0;
            return -1;
        }
        if (out_leidos) *out_leidos = leidos;
        return 0;
    }
    return ((TR_SOLFS_READ)(ULONG_PTR)TR_FN_READ)(handle, buf, tam, out_leidos);
}

static int WINAPI tr_mi_info(DWORD handle, void *buf)
{
    if (tr_slot_de(handle)) return 0; /* el llamador 0x72FF70 ya puso el búfer de 48 B en cero */
    return ((TR_SOLFS_INFO)(ULONG_PTR)TR_FN_INFO)(handle, buf);
}

static int tr_exe_conocido(void)
{
    BYTE *b = (BYTE *)GetModuleHandleA(NULL);
    if ((ULONG_PTR)b != TR_EXE_BASE || !legible(b, 0x40)) return 0;
    IMAGE_NT_HEADERS32 *nt = (IMAGE_NT_HEADERS32 *)(b + ((IMAGE_DOS_HEADER *)b)->e_lfanew);
    if (!legible(nt, sizeof(*nt))) return 0;
    return nt->FileHeader.TimeDateStamp == TR_EXE_SELLO && nt->OptionalHeader.SizeOfImage == TR_EXE_TAMANO;
}

static void *tr_gancho_de(int op)
{
    switch (op) {
    case TR_OP_OPEN:  return (void *)tr_mi_open;
    case TR_OP_CLOSE: return (void *)tr_mi_close;
    case TR_OP_SIZE:  return (void *)tr_mi_size;
    case TR_OP_SEEK:  return (void *)tr_mi_seek;
    case TR_OP_POS:   return (void *)tr_mi_pos;
    case TR_OP_READ:  return (void *)tr_mi_read;
    case TR_OP_INFO:  return (void *)tr_mi_info;
    default:          return NULL;
    }
}

static int tr_parchear_cadenas_es(void)
{
    int hechas = 0;
    for (int i = 0; i < TR_NCADENAS; i++) {
        const TR_CADENA_ES *c = &TR_CADENAS_ES[i];
        size_t n = strlen(c->orig);
        if (strlen(c->nuevo) != n) continue;
        size_t bytes = (n + 1) * 2;
        BYTE *p = (BYTE *)(ULONG_PTR)c->va;
        if (!legible(p, bytes) || !tr_coincide_utf16(p, c->orig)) {
            apuntar("  [traduccion] ⚠ cadena exe 0x%lX («%s») no coincide: no se toca", c->va, c->orig);
            continue;
        }
        DWORD prot;
        if (!VirtualProtect(p, bytes, PAGE_READWRITE, &prot)) continue;
        tr_escribir_utf16(p, c->nuevo);
        VirtualProtect(p, bytes, prot, &prot);
        hechas++;
    }
    return hechas;
}

typedef void *(__fastcall *TR_CREATE_GLYPH)(void *self, void *edx_unused, DWORD ch);
typedef int (__cdecl *TR_FT_LOAD_GLYPH)(void *face, DWORD gid, int load_flags);

static void tr_volcar_bitmap_ft(const char *etiq, const BYTE *buf, int bw, int bh, int pitch, unsigned char pmode)
{
    static const char PAL[11] = " .:-=+*#%@";
    if (!buf || bw <= 0 || bh <= 0) {
        apuntar("  [diag-glifo]   %s: (vacío %dx%d)", etiq, bw, bh);
        return;
    }
    int mw = bw > 32 ? 32 : bw;
    int mh = bh > 24 ? 24 : bh;
    for (int y = 0; y < mh; y++) {
        char fila[40];
        const BYTE *src = buf + (SIZE_T)y * (SIZE_T)pitch;
        for (int x = 0; x < mw; x++) {
            int v = 0;
            if (pmode == 1) {
                v = (src[x >> 3] & (0x80 >> (x & 7))) ? 255 : 0;
                fila[x] = v ? '#' : '.';
            } else {
                v = src[x];
                fila[x] = PAL[(v * 9) / 255];
            }
        }
        fila[mw] = 0;
        apuntar("  [diag-glifo]   %s y=%02d |%s|", etiq, y, fila);
    }
}

static void tr_probar_flag_ft(void *face, DWORD gid, int flag, const char *etiq)
{
    int rc = ((TR_FT_LOAD_GLYPH)(ULONG_PTR)TR_FN_FT_LOAD_GLYPH)(face, gid, flag);
    if (rc != 0) {
        apuntar("  [diag-glifo]   %s: FT_Load_Glyph err=%d", etiq, rc);
        return;
    }
    const BYTE *slot = *(const BYTE *const *)((const BYTE *)face + 0x54);
    if (!slot || !legible(slot, 0x6C)) return;
    int adv_raw = *(const int *)(slot + 0x40);
    int bh = *(const int *)(slot + 0x4C);
    int bw = *(const int *)(slot + 0x50);
    int pitch = *(const int *)(slot + 0x54);
    const BYTE *buf = *(const BYTE *const *)(slot + 0x58);
    unsigned char pmode = *(const unsigned char *)(slot + 0x5E);
    int bleft = *(const int *)(slot + 0x64);
    int btop = *(const int *)(slot + 0x68);
    apuntar("  [diag-glifo]   %s: bmp=%dx%d left=%d top=%d adv=%d (raw=%d/64) pmode=%u pitch=%d",
            etiq, bw, bh, bleft, btop, adv_raw >> 6, adv_raw, (unsigned)pmode, pitch);
    tr_volcar_bitmap_ft(etiq, buf, bw, bh, pitch, pmode);
}

static void *__fastcall tr_mi_create_glyph(void *self, void *edx_unused, DWORD ch_arg)
{
    (void)edx_unused;
    void *res = ((TR_CREATE_GLYPH)(ULONG_PTR)TR_FN_CREATE_GLYPH)(self, NULL, ch_arg);
    unsigned short ch = (unsigned short)(ch_arg & 0xFFFFu);
    if (!res || !tr_es_glifo_diag(ch)) return res;
    LONG n = InterlockedIncrement(&g_tr_diag_n);
    if (n > 48) return res;
    if (!legible(res, 0x28) || !self || !legible(self, 0x10)) return res;
    const DWORD *g = (const DWORD *)res;
    void *htex = (void *)(ULONG_PTR)g[0];
    DWORD gid = g[1];
    int adv = (int)g[2];
    DWORD fsz = g[3];
    int tw = (int)g[4], th = (int)g[5];
    int bw = (int)g[6], bh = (int)g[7];
    int bleft = (int)g[8], btop = (int)g[9];

    void *face = *(void *const *)((const BYTE *)self + 8);
    const BYTE *slot = (face && legible(face, 0x58)) ? *(const BYTE *const *)((const BYTE *)face + 0x54) : NULL;
    int adv_raw = 0, ft_pitch = 0;
    unsigned char pmode = 0;
    const BYTE *ft_buf = NULL;
    if (slot && legible(slot, 0x6C)) {
        adv_raw = *(const int *)(slot + 0x40);
        ft_pitch = *(const int *)(slot + 0x54);
        ft_buf = *(const BYTE *const *)(slot + 0x58);
        pmode = *(const unsigned char *)(slot + 0x5E);
    }

    /* Inspeccionar la textura D3D9 recién llenada (sólo lectura): pitch real, diferencias y basura fuera de caja */
    DWORD d3d_fmt = 0, d3d_w = 0, d3d_h = 0, d3d_pitch = 0;
    int diff = -1, basura = -1;
    void *tex = (htex && legible(htex, 4)) ? *(void *const *)htex : NULL;
    if (tex && legible(tex, 4)) {
        void **vt = *(void ***)tex;
        DWORD desc[8] = {0};
        if (vt && legible(vt, 21 * sizeof(void *))
            && ((long (WINAPI *)(void *, UINT, void *))vt[17])(tex, 0, desc) == 0) {
            d3d_fmt = desc[0];
            d3d_w = desc[6];
            d3d_h = desc[7];
            DWORD lr[2] = {0, 0};
            if (((long (WINAPI *)(void *, UINT, void *, const RECT *, DWORD))vt[19])(tex, 0, lr, NULL, 0x10) == 0) {
                d3d_pitch = lr[0];
                const BYTE *bits = (const BYTE *)(ULONG_PTR)lr[1];
                diff = 0;
                basura = 0;
                for (int y = 0; y < (int)d3d_h; y++) {
                    const DWORD *row = (const DWORD *)(bits + (SIZE_T)y * d3d_pitch);
                    for (int x = 0; x < (int)d3d_w; x++) {
                        unsigned char a = (unsigned char)(row[x] >> 24);
                        if (x < bw && y < bh && ft_buf) {
                            unsigned char fa = 0;
                            if (pmode == 1) fa = (ft_buf[(SIZE_T)y * ft_pitch + (x >> 3)] & (0x80 >> (x & 7))) ? 255 : 0;
                            else fa = ft_buf[(SIZE_T)y * ft_pitch + x];
                            if (a != fa) diff++;
                        } else if (a != 0) {
                            basura++;
                        }
                    }
                }
                ((long (WINAPI *)(void *, UINT))vt[20])(tex, 0);
            }
        }
    }

    apuntar("  [diag-glifo] #%ld '%s' (U+%04X) fs=%lu gid=%lu | bmp=%dx%d left=%d top=%d adv=%d (raw=%d/64) pmode=%u ft_pitch=%d | tex=%dx%d d3d=%lux%lu fmt=%lu pitch=%lu (esp=%d) | diff=%d basura=%d",
            (long)n, tr_nombre_glifo_diag(ch), (unsigned)ch, (unsigned long)fsz, (unsigned long)gid,
            bw, bh, bleft, btop, adv, adv_raw, (unsigned)pmode, ft_pitch,
            tw, th, (unsigned long)d3d_w, (unsigned long)d3d_h, (unsigned long)d3d_fmt,
            (unsigned long)d3d_pitch, tw * 4, diff, basura);
    tr_volcar_bitmap_ft("default(4)", ft_buf, bw, bh, ft_pitch, pmode);

    /* Comparación A/B en caliente (sin tocar la textura ya creada; al final restaura FT_LOAD_RENDER=4) */
    if (face && gid && ((ch == 0x00F1u && ++g_tr_diag_cmp_enie <= 3) || (ch == 0x00F3u && ++g_tr_diag_cmp_oac <= 2))) {
        tr_probar_flag_ft(face, gid, 0x00010004, "light(0x10004)");
        tr_probar_flag_ft(face, gid, 0x00000006, "nohint(0x6)");
        ((TR_FT_LOAD_GLYPH)(ULONG_PTR)TR_FN_FT_LOAD_GLYPH)(face, gid, 4);
    }
    return res;
}

static void tr_instalar_diag_glifos(void)
{
    if (!g_tr_diag_glifos) return;
    const BYTE *sitio = (const BYTE *)(ULONG_PTR)TR_SITIO_CREATE_GLYPH;
    const BYTE *fn_cg = (const BYTE *)(ULONG_PTR)TR_FN_CREATE_GLYPH;
    const BYTE *fn_fl = (const BYTE *)(ULONG_PTR)TR_FN_FT_LOAD_GLYPH;
    if (!legible(sitio, 5) || !tr_es_llamada(sitio, TR_SITIO_CREATE_GLYPH, TR_FN_CREATE_GLYPH)
        || !legible(fn_cg, 8) || memcmp(fn_cg, TR_PROLOGO_CREATE_GLYPH, 8) != 0
        || !legible(fn_fl, 8) || memcmp(fn_fl, TR_PROLOGO_FT_LOAD, 8) != 0) {
        apuntar("  [traduccion] ⚠ diag_glifos: bytes en 0x771FF1/0x770A00/0x81DD30 no coinciden: no se engancha");
        return;
    }
    BYTE *p = (BYTE *)(ULONG_PTR)TR_SITIO_CREATE_GLYPH;
    LONG rel = (LONG)((ULONG_PTR)(void *)tr_mi_create_glyph - (TR_SITIO_CREATE_GLYPH + 5u));
    DWORD prot;
    if (!VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &prot)) return;
    memcpy(p + 1, &rel, 4);
    VirtualProtect(p, 5, prot, &prot);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    g_tr_diag_instalado = 1;
    apuntar("  [traduccion] diag_glifos: enganchado CreateGlyph (0x771FF1) para medir ñ, Ñ, ó, n, ü en eda_d3d9.log");
}

static void tr_instalar(void)
{
    if (!g_mejoras) {
        if (g_tr_idioma_cfg[0])
            apuntar("  [traduccion] desactivada por [general] mejoras=0 (idioma pedido: «%s»)", g_tr_idioma_cfg);
        return;
    }
    if (!tr_idioma_activo(g_tr_idioma_cfg, g_mejoras, g_tr_idioma)) {
        apuntar("  [traduccion] apagada (idioma=«%s»): el juego lee Data.dat como siempre",
                g_tr_idioma_cfg[0] ? g_tr_idioma_cfg : "vacío");
        return;
    }
    /* Comprobar si existe carpeta suelta traducciones\<idioma>\ junto a la dll (prioridad sobre embebidos) */
    g_tr_carpeta_suelta = 0;
    if (g_tr_base_w[0]) {
        unsigned short carp_w[MAX_PATH];
        unsigned short dummy[2] = {'a', 0};
        if (tr_armar_ruta((const unsigned short *)g_tr_base_w, g_tr_idioma, dummy, carp_w, MAX_PATH)) {
            size_t clen = 0;
            while (carp_w[clen]) clen++;
            if (clen >= 2) carp_w[clen - 2] = 0;
            DWORD attr = GetFileAttributesW((const WCHAR *)carp_w);
            if (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY))
                g_tr_carpeta_suelta = 1;
        }
    }
    int n_emb = tr_contar_embebidos(g_tr_idioma);
    if (!g_tr_carpeta_suelta && n_emb == 0) {
        apuntar("  [traduccion] idioma=%s: sin carpeta traducciones\\%s\\ ni archivos embebidos: sin ganchos",
                g_tr_idioma, g_tr_idioma);
        return;
    }
    if (!tr_exe_conocido()) {
        apuntar("  [traduccion] ⚠ no es el EDA_limpio.exe conocido (sello/tamaño del PE distintos): no se engancha nada");
        return;
    }
    /* Verificación ATÓMICA previa: los 7 prólogos y las 16 llamadas E8 deben coincidir TODOS antes de tocar 1 byte */
    for (int i = 0; i < TR_NPROLOGOS; i++) {
        const BYTE *p = (const BYTE *)(ULONG_PTR)TR_PROLOGOS[i].fn;
        if (!legible(p, 8) || memcmp(p, TR_PROLOGOS[i].bytes, 8) != 0) {
            apuntar("  [traduccion] ⚠ prólogo de %s (0x%lX) no coincide: no se engancha nada",
                    TR_PROLOGOS[i].nombre, TR_PROLOGOS[i].fn);
            return;
        }
    }
    for (int i = 0; i < TR_NSITIOS; i++) {
        const BYTE *p = (const BYTE *)(ULONG_PTR)TR_SITIOS[i].sitio;
        if (!legible(p, 5) || !tr_es_llamada(p, TR_SITIOS[i].sitio, TR_SITIOS[i].destino)) {
            apuntar("  [traduccion] ⚠ llamada en 0x%lX (%s) no coincide con EDA_limpio.exe: no se engancha nada",
                    TR_SITIOS[i].sitio, TR_SITIOS[i].quien);
            return;
        }
    }
    InitializeCriticalSection(&g_tr_cs);
    for (int i = 0; i < TR_MAX_SLOTS; i++) {
        g_tr_slots[i].fh = INVALID_HANDLE_VALUE;
        g_tr_slots[i].mem = NULL;
        g_tr_slots[i].mem_tam = 0u;
        g_tr_slots[i].mem_pos = 0u;
        g_tr_slots[i].en_uso = 0;
    }
    int puestos = 0;
    for (int i = 0; i < TR_NSITIOS; i++) {
        BYTE *p = (BYTE *)(ULONG_PTR)TR_SITIOS[i].sitio;
        void *nuevo = tr_gancho_de(TR_SITIOS[i].op);
        if (!nuevo) continue;
        LONG rel = (LONG)((ULONG_PTR)nuevo - (TR_SITIOS[i].sitio + 5u));
        DWORD prot;
        if (!VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &prot)) continue;
        memcpy(p + 1, &rel, 4);
        VirtualProtect(p, 5, prot, &prot);
        FlushInstructionCache(GetCurrentProcess(), p, 5);
        puestos++;
    }
    g_tr_instalado = (puestos == TR_NSITIOS);
    int cad = 0;
    if (g_tr_instalado && g_tr_cadenas_exe && strcmp(g_tr_idioma, "es") == 0)
        cad = tr_parchear_cadenas_es();
    apuntar("  [traduccion] idioma=%s · %d/%d llamadas SolFS enganchadas · %d embebido(s) · carpeta suelta: %s · cadenas exe %d/%d",
            g_tr_idioma, puestos, TR_NSITIOS, n_emb, g_tr_carpeta_suelta ? "sí" : "no", cad, TR_NCADENAS);
    if (g_tr_instalado) tr_instalar_diag_glifos();
}

static void tr_cerrar(void)
{
    if (!g_tr_instalado) return;
    apuntar("  [traduccion] resumen: %ld archivo(s) redirigido(s) (%ld suelto(s), %ld embebido(s)) · idioma=%s%s",
            (long)g_tr_redirigidos, (long)g_tr_redirigidos_sueltos, (long)g_tr_redirigidos_emb,
            g_tr_idioma, g_tr_diag_instalado ? " · diag_glifos activo" : "");
    if (g_tr_diag_instalado)
        apuntar("  [traduccion] diag_glifos: %ld glifo(s) medido(s) en eda_d3d9.log ([diag-glifo])", (long)g_tr_diag_n);
    for (int i = 0; i < TR_MAX_SLOTS; i++) {
        if (g_tr_slots[i].en_uso) {
            if (g_tr_slots[i].fh != INVALID_HANDLE_VALUE) CloseHandle(g_tr_slots[i].fh);
            g_tr_slots[i].fh = INVALID_HANDLE_VALUE;
            g_tr_slots[i].mem = NULL;
            g_tr_slots[i].mem_tam = 0u;
            g_tr_slots[i].mem_pos = 0u;
            g_tr_slots[i].en_uso = 0;
        }
    }
}

#endif /* !EDA_TRADUCCION_SOLO_LOGICA */
