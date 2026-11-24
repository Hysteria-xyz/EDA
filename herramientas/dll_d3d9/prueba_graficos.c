/* prueba_graficos.c — ★ (Punto 6) las cuentas de eda_graficos.c sin Windows ni el juego.
 *     gcc -std=gnu11 -o /tmp/pg herramientas/dll_d3d9/prueba_graficos.c && /tmp/pg */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned long DWORD; typedef unsigned char BYTE; typedef unsigned int UINT; typedef long LONG;
typedef unsigned long ULONG_PTR; typedef int BOOL; typedef void *HWND;
typedef struct { LONG left, top, right, bottom; } RECT;
#define WINAPI
#define VT(o) (*(void ***)(o))
#define InterlockedIncrement(p) (++*(p))
#define InterlockedExchange(p, v) (*(p) = (v))
#define lstrcpynA(d, s, n) (strncpy(d, s, (n) - 1), (d)[(n) - 1] = 0)
#define lstrcmpiA strcasecmp
#define wsprintfA sprintf
#define PAGE_EXECUTE_READWRITE 0x40
static int g_apuntes, g_diagnostico;
static void apuntar(const char *f, ...) { (void)f; g_apuntes++; }
static int legible(const void *p, size_t n) { (void)p; (void)n; return 0; }
static int VirtualProtect(void *a, size_t n, DWORD p, DWORD *v) { (void)a; (void)n; (void)p; (void)v; return 0; }
static void FlushInstructionCache(void *a, void *b, size_t c) { (void)a; (void)b; (void)c; }
static void *GetCurrentProcess(void) { return 0; }
static void poner(void **vt, int i, void *nuevo, void **viejo) { *viejo = vt[i]; vt[i] = nuevo; }
static char g_ini_v[16][2][40]; static int g_ini_n;
static int GetPrivateProfileIntA(const char *a, const char *k, int d, const char *f)
{ (void)a; (void)f; for (int i = 0; i < g_ini_n; i++) if (!strcmp(g_ini_v[i][0], k)) return atoi(g_ini_v[i][1]); return d; }
static int GetPrivateProfileStringA(const char *a, const char *k, const char *d, char *o, int n, const char *f)
{ (void)a; (void)f; for (int i = 0; i < g_ini_n; i++) if (!strcmp(g_ini_v[i][0], k)) { lstrcpynA(o, g_ini_v[i][1], n); return 1; } lstrcpynA(o, d, n); return 0; }
static int WritePrivateProfileStringA(const char *a, const char *k, const char *v, const char *f)
{ (void)a; (void)f; for (int i = 0; i < g_ini_n; i++) if (!strcmp(g_ini_v[i][0], k)) { strcpy(g_ini_v[i][1], v); return 1; }
  strcpy(g_ini_v[g_ini_n][0], k); strcpy(g_ini_v[g_ini_n++][1], v); return 1; }
static int GetEnvironmentVariableA(const char *n, char *o, int c) { (void)n; (void)o; (void)c; return 0; }
typedef void *HDC; typedef const unsigned short *LPCWSTR;
static DWORD g_hilo = 7;
static DWORD GetCurrentThreadId(void) { return g_hilo; }
static void *parchear_iat(const char *d, const char *f, void *n) { (void)d; (void)f; (void)n; return 0; }
/* lo de eda_d3d9.c / eda_escala2d.c que usa */
enum { I_BEGINSCENE = 41, I_ENDSCENE = 42, I_SETRS = 57, I_CREATESB = 59, I_SETTEXTURE = 65, I_SETTSS = 67, I_DPUP = 83,
       I_SETFVF = 89, I_SETVS = 92, I_SETPS = 107 };
typedef long (WINAPI *M_SIN)(void *); typedef long (WINAPI *M_RS)(void *, DWORD, DWORD);
typedef long (WINAPI *M_TSS)(void *, DWORD, DWORD, DWORD); typedef long (WINAPI *M_PTR)(void *, DWORD, void *);
typedef long (WINAPI *M_UNO)(void *, void *); typedef long (WINAPI *M_DPUP)(void *, DWORD, UINT, const void *, UINT);
typedef long (WINAPI *M_CSB)(void *, DWORD, void **); typedef long (WINAPI *M_SB)(void *);
static int g_e2d_w = 1920, g_e2d_h = 1080, g_e2d_activa = 1, g_e2d_es_orto = 1;
static int g_e2d_ambiente = 1, g_e2d_stage_ahora, g_e2d_res_fase;     /* (las franjas con ambiente) */
static float g_e2d_s = 1.8f, g_e2d_rx = 240, g_e2d_ry;
static int g_e2d_lienzo = 800;                                       /* (el lienzo: 800 salvo el lobby panorámico) */
#define FALSE 0
static volatile long g_e2d_propio, g_e2d_rt_fuera;
static long c_e2d_rt_fuera;
typedef unsigned short WORD; typedef unsigned long ULONG; typedef size_t SIZE_T;
static void *GetProcessHeap(void) { return 0; }
static void *HeapAlloc(void *h, int f, size_t n) { (void)h; (void)f; return malloc(n); }
static int HeapFree(void *h, int f, void *p) { (void)h; (void)f; free(p); return 1; }
/* GDI de mentira: una "letra" es un rectángulo de tinta del tamaño de su caja (al doble si la fuente es el doble) */
#define __fastcall
typedef void *HFONT, *HBITMAP, *HGDIOBJ; typedef unsigned short WCHAR;
typedef struct { LONG lfHeight, lfWidth; BYTE lfQuality; } LOGFONTW;
typedef struct { struct { DWORD biSize; LONG biWidth, biHeight; WORD biPlanes, biBitCount; } bmiHeader; } BITMAPINFO;
#define OBJ_FONT 6
#define TRANSPARENT 1
#define RGB(r, g, b) ((DWORD)(r) | ((DWORD)(g) << 8) | ((DWORD)(b) << 16))
static LOGFONTW g_fuente = {-12, 0, 3}, g_fuente_dc;
static int g_caja[256][4];                 /* L,T,R,B de cada letra (en la fuente original) */
static BYTE *g_dib; static int g_dib_w, g_dib_h, g_textos;
static HGDIOBJ GetCurrentObject(HDC d, int t) { (void)d; (void)t; return &g_fuente; }
static int GetObjectW(HGDIOBJ o, int n, void *p) { memcpy(p, o, sizeof(LOGFONTW)); return n; }
static HFONT CreateFontIndirectW(const LOGFONTW *l) { g_fuente_dc = *l; return &g_fuente_dc; }
static HDC CreateCompatibleDC(HDC d) { (void)d; return (HDC)1; }
static HBITMAP CreateDIBSection(HDC d, const BITMAPINFO *b, int u, void **bits, void *s, DWORD o)
{ (void)d; (void)u; (void)s; (void)o; g_dib_w = b->bmiHeader.biWidth; g_dib_h = -b->bmiHeader.biHeight;
  g_dib = calloc((size_t)g_dib_w * g_dib_h, 4); *bits = g_dib; return g_dib; }
static HGDIOBJ SelectObject(HDC d, HGDIOBJ o) { (void)d; return o; }
static UINT GetTextAlign(HDC d) { (void)d; return 0; }
static UINT SetTextAlign(HDC d, UINT a) { (void)d; return a; }
static DWORD SetTextColor(HDC d, DWORD c) { (void)d; return c; }
static int SetBkMode(HDC d, int m) { (void)d; return m; }
static BOOL TextOutW(HDC d, int x, int y, const WCHAR *t, int n)
{ (void)d; (void)n; int k = g_fuente_dc.lfHeight / g_fuente.lfHeight; const int *c = g_caja[*t & 255]; g_textos++;
  for (int yy = y + c[1] * k; yy < y + c[3] * k + 1; yy++) for (int xx = x + c[0] * k; xx < x + c[2] * k + 1; xx++)   /* (+1: se sale) */
    if (xx >= 0 && yy >= 0 && xx < g_dib_w && yy < g_dib_h) g_dib[(yy * g_dib_w + xx) * 4 + 1] = 255;
  return 1; }
typedef struct { LONG tmHeight, tmAscent; } TEXTMETRICW;
static int g_vf_caja[256][4];              /* fuentes del motor: caja negra bbX,bbY y origen ox,oy (a escala 1) */
static int g_vf_asc = 8;
static BOOL GetTextMetricsW(HDC d, TEXTMETRICW *t) { (void)d; int k = g_fuente_dc.lfHeight / g_fuente.lfHeight; t->tmAscent = g_vf_asc * k; t->tmHeight = 12 * k; return 1; }
static BOOL TextOutA(HDC d, int x, int y, const char *t, int n)
{ (void)d; (void)n; int k = g_fuente_dc.lfHeight / g_fuente.lfHeight; const int *c = g_vf_caja[(BYTE)*t]; g_textos++;
  int x0 = x + c[2] * k, y0 = y + (g_vf_asc - c[3]) * k;               /* (TA_TOP: la caja negra, con su línea de base en ascent) */
  for (int yy = y0; yy < y0 + c[1] * k; yy++) for (int xx = x0; xx < x0 + c[0] * k; xx++)
    if (xx >= 0 && yy >= 0 && xx < g_dib_w && yy < g_dib_h) g_dib[(yy * g_dib_w + xx) * 4] = 255;
  return 1; }
static BOOL GdiFlush(void) { return 1; }
static BOOL DeleteObject(HGDIOBJ o) { if (o == g_dib) { free(g_dib); g_dib = NULL; } return 1; }
static BOOL DeleteDC(HDC d) { (void)d; return 1; }
static int IsBadReadPtr(const void *p, size_t n) { (void)p; (void)n; return 1; }
static int g_e2d_activa_prueba;
#define MAX_PATH 260
#define lstrlenA(s) ((int)strlen(s))
static char g_log[MAX_PATH] = "/tmp/eda_prueba.log";
#include "eda_graficos.c"

static int ok, mal;
static void chequear(const char *q, int si) { printf("  %s  %s\n", si ? "OK " : "MAL", q); if (si) ok++; else mal++; }
/* un SetSamplerState de mentira: anota lo último por tipo */
static DWORD g_ss[16];
static long WINAPI sss_falso(void *d, DWORD s, DWORD t, DWORD v) { (void)d; (void)s; if (t < 16) g_ss[t] = v; return 0; }
/* un IDirect3D9 de mentira: CheckDeviceMultiSampleType acepta hasta g_aa_hw */
static int g_aa_hw = 4;
static long WINAPI cms_falso(void *d, UINT a, DWORD t, DWORD f, BOOL w, DWORD ms, DWORD *q) { (void)d; (void)a; (void)t; (void)f; (void)w; *q = 1; return (int)ms <= g_aa_hw ? 0 : -1; }
static void *g_d3d_vt[16];
static void *g_d3d_obj = g_d3d_vt;

/* ── el atlas de mentira ── */
typedef struct { void **vt; unsigned short *px; int w, h; DWORD fmt; } TEX;
static void *g_tex_vt[24], *g_gem_vt[24], *g_dev_vt[80];
static void *g_gemelo_creado, *g_settex_ultima, *g_settex_otra, *g_tex_otra_ptr;
static int g_otra_cambiada;
static DWORD *g_gem_px;
static DWORD WINAPI t_tipo(void *t) { (void)t; return 3; }
static DWORD WINAPI t_niveles(void *t) { (void)t; return 1; }
static long WINAPI t_desc(void *o, UINT l, DWORD *d) { TEX *t = (TEX *)o; (void)l; memset(d, 0, 8 * sizeof(DWORD)); d[0] = t->fmt; d[3] = 1; d[6] = (DWORD)t->w; d[7] = (DWORD)t->h; return 0; }
static long WINAPI t_lock(void *o, UINT l, DWORD *lr, const RECT *r, DWORD f) { TEX *t = (TEX *)o; (void)l; (void)r; (void)f; lr[0] = (DWORD)(t->w * 2); lr[1] = (DWORD)(ULONG_PTR)t->px; return 0; }
static long WINAPI t_unlock(void *o, UINT l) { (void)o; (void)l; return 0; }
static ULONG WINAPI t_ref(void *o) { (void)o; return 1; }
static TEX g_gem;
static long WINAPI g_lock(void *o, UINT l, DWORD *lr, const RECT *r, DWORD f) { (void)o; (void)l; (void)r; (void)f; lr[0] = (DWORD)(g_gem.w * sizeof(DWORD)); lr[1] = (DWORD)(ULONG_PTR)g_gem_px; return 0; }
static TEX g_gem_ini = {g_gem_vt, 0, 128, 128, 21};
static long WINAPI d_ctex(void *d, UINT w, UINT h, UINT n, DWORD u, DWORD f, DWORD p, void **t, void *c)
{ (void)d; (void)n; (void)u; (void)p; (void)c; if (w != 128 || h != 128 || f != 21) return -1; g_gem_px = calloc(128 * 128, sizeof(DWORD)); *t = &g_gem; g_gemelo_creado = &g_gem; return 0; }
static long WINAPI d_settex(void *d, DWORD e, void *t) { (void)d; (void)e; g_settex_ultima = t; return 0; }
static void *g_tx_vt[24];
static BOOL WINAPI f_toutw(HDC a, int b, int c, LPCWSTR d, int e) { (void)a; (void)b; (void)c; (void)d; (void)e; return 1; }
static void *g_txt_a_crear;
static int g_gem_hecho, g_rel_cero;
static long WINAPI t_lock32(void *o, UINT l, DWORD *lr, const RECT *r, DWORD f)
{ TEX *t = (TEX *)o; (void)l; (void)r; (void)f; lr[0] = (DWORD)(t->w * 4); lr[1] = (DWORD)(ULONG_PTR)t->px; return 0; }
static ULONG WINAPI t_rel(void *o) { (void)o; return g_rel_cero ? 0 : 1; }
static long WINAPI f_ctex_txt(void *d, UINT w, UINT h, UINT n, DWORD u, DWORD f, DWORD p, void **t, void *c)
{
    (void)d; (void)w; (void)h; (void)n; (void)u; (void)f; (void)p; (void)c;
    if (g_txt_a_crear == &g_gem) { free(g_gem_px); g_gem_px = calloc((size_t)w * h, sizeof(DWORD)); g_gem.vt = g_gem_vt; g_gem_hecho++; }
    *t = g_txt_a_crear ? g_txt_a_crear : (void *)&g_gem;
    return 0;
}
static int gr_prueba_atlas(unsigned short *letras, unsigned short *otra)
{
    static TEX tl, to;
    g_tex_vt[1] = (void *)t_ref; g_tex_vt[2] = (void *)t_ref; g_tex_vt[10] = (void *)t_tipo; g_tex_vt[13] = (void *)t_niveles;
    g_tex_vt[17] = (void *)t_desc; g_tex_vt[19] = (void *)t_lock; g_tex_vt[20] = (void *)t_unlock;
    memcpy(g_gem_vt, g_tex_vt, sizeof(g_gem_vt)); g_gem_vt[19] = (void *)g_lock; g_gem = g_gem_ini;
    tl.vt = g_tex_vt; tl.px = letras; tl.w = 64; tl.h = 64; tl.fmt = 26;
    to.vt = g_tex_vt; to.px = otra; to.w = 64; to.h = 64; to.fmt = 26;
    g_tex_otra_ptr = &to;
    g_dev_vt[23] = (void *)d_ctex;
    void *dev = g_dev_vt; *(void ***)dev = g_dev_vt; g_dev_vt[23] = (void *)d_ctex;
    g_gr_settex_real = d_settex;
    g_gr_letras = 2;                                     /* (los gemelos de prueba: letras=2) */
    gr_settex(dev, 0, &tl);
    void *primera = g_settex_ultima;
    gr_settex(dev, 0, &to);
    g_settex_otra = g_settex_ultima;
    g_otra_cambiada = g_settex_otra != &to;
    gr_settex(dev, 0, &tl);
    g_settex_ultima = primera == g_settex_ultima ? g_settex_ultima : NULL;
    return g_gr_fu_n == 1 && g_gemelo_creado && (g_gem_px[64 * 128 + 64] >> 24) <= 255;
}


/* ── (20-nov) un dispositivo de mentira con la regla de Direct3D9 para el Reset: falla (INVALIDCALL) si queda VIVO un
 *   recurso del pool DEFAULT; un recurso PUESTO (SetTexture / SetStreamSource / SetIndices / SetRenderTarget) sigue vivo
 *   aunque su dueño lo haya soltado (como en Windows; pruebas de Wine «bound but otherwise not referenced»). ── */
typedef struct { void **vt; int ref, puesto; DWORD pool, uso, w, h, tipo; } REC;
static void *r_tex_vt[24], *r_vb_vt[16], *r_sup_vt[16], *r_dev_vt[110];
static REC *r_tex[21], *r_vb[16], *r_ib, *r_rt[4], *r_ds, r_bb;
static REC *r_todos[16]; static int r_n;
static ULONG WINAPI r_addref(void *o) { return (ULONG)++((REC *)o)->ref; }
static ULONG WINAPI r_release(void *o) { REC *r = (REC *)o; if (r->ref > 0) r->ref--; return (ULONG)r->ref; }
static DWORD WINAPI r_tipo(void *o) { return ((REC *)o)->tipo; }
static long WINAPI r_tdesc(void *o, UINT l, DWORD *d) { REC *r = (REC *)o; (void)l; memset(d, 0, 8 * sizeof(DWORD)); d[2] = r->uso; d[3] = r->pool; d[6] = r->w; d[7] = r->h; return 0; }
static long WINAPI r_bdesc(void *o, DWORD *d) { REC *r = (REC *)o; memset(d, 0, 8 * sizeof(DWORD)); d[2] = r->uso; d[3] = r->pool; d[4] = r->w; return 0; }
static long WINAPI r_sdesc(void *o, DWORD *d) { REC *r = (REC *)o; memset(d, 0, 8 * sizeof(DWORD)); d[3] = r->pool; d[6] = r->w; d[7] = r->h; return 0; }
static void r_poner(REC **lugar, REC *nuevo) { if (*lugar) (*lugar)->puesto--; *lugar = nuevo; if (nuevo) nuevo->puesto++; }
static long WINAPI r_gettex(void *d, DWORD s, void **t) { (void)d; DWORD i = s < 16 ? s : 16 + (s - 256); *t = i < 21 ? r_tex[i] : NULL; if (*t) r_addref(*t); return 0; }
static long WINAPI r_settex(void *d, DWORD s, void *t) { (void)d; DWORD i = s < 16 ? s : 16 + (s - 256); if (i < 21) r_poner(&r_tex[i], (REC *)t); return 0; }
static long WINAPI r_getss(void *d, UINT i, void **v, UINT *a, UINT *b) { (void)d; *a = *b = 0; *v = r_vb[i]; if (*v) r_addref(*v); return 0; }
static long WINAPI r_setss(void *d, UINT i, void *v, UINT a, UINT b) { (void)d; (void)a; (void)b; r_poner(&r_vb[i], (REC *)v); return 0; }
static long WINAPI r_getib(void *d, void **v) { (void)d; *v = r_ib; if (*v) r_addref(*v); return 0; }
static long WINAPI r_setib(void *d, void *v) { (void)d; r_poner(&r_ib, (REC *)v); return 0; }
static long WINAPI r_getrt(void *d, DWORD i, void **v) { (void)d; *v = r_rt[i]; if (*v) r_addref(*v); return 0; }
static long WINAPI r_setrt(void *d, DWORD i, void *v) { (void)d; r_poner(&r_rt[i], (REC *)v); return 0; }
static long WINAPI r_getbb(void *d, UINT a, UINT b, DWORD c, void **v) { (void)d; (void)a; (void)b; (void)c; *v = &r_bb; r_addref(&r_bb); return 0; }
static long WINAPI r_getds(void *d, void **v) { (void)d; *v = r_ds; if (*v) r_addref(*v); return 0; }
static long WINAPI r_setds(void *d, void *v) { (void)d; r_poner(&r_ds, (REC *)v); return 0; }
static long WINAPI r_reset(void *d, void *pp)
{
    (void)d; (void)pp;
    for (int i = 0; i < r_n; i++) if (r_todos[i]->pool == 0 && (r_todos[i]->ref > 0 || r_todos[i]->puesto > 0)) return (long)0x8876086C;
    return 0;
}
static REC *r_nuevo(void **vt, DWORD tipo, DWORD pool, DWORD uso, DWORD w, DWORD h)
{
    REC *r = calloc(1, sizeof(REC)); r->vt = vt; r->ref = 1; r->tipo = tipo; r->pool = pool; r->uso = uso; r->w = w; r->h = h;
    r_todos[r_n++] = r; return r;
}
static void r_armar(void)
{
    r_tex_vt[1] = (void *)r_addref; r_tex_vt[2] = (void *)r_release; r_tex_vt[10] = (void *)r_tipo; r_tex_vt[17] = (void *)r_tdesc;
    r_vb_vt[1] = (void *)r_addref; r_vb_vt[2] = (void *)r_release; r_vb_vt[13] = (void *)r_bdesc;
    r_sup_vt[1] = (void *)r_addref; r_sup_vt[2] = (void *)r_release; r_sup_vt[12] = (void *)r_sdesc;
    r_dev_vt[16] = (void *)r_reset; r_dev_vt[18] = (void *)r_getbb; r_dev_vt[37] = (void *)r_setrt; r_dev_vt[38] = (void *)r_getrt;
    r_dev_vt[39] = (void *)r_setds; r_dev_vt[40] = (void *)r_getds; r_dev_vt[64] = (void *)r_gettex; r_dev_vt[65] = (void *)r_settex;
    r_dev_vt[100] = (void *)r_setss; r_dev_vt[101] = (void *)r_getss; r_dev_vt[104] = (void *)r_setib; r_dev_vt[105] = (void *)r_getib;
    r_bb.vt = r_sup_vt; r_bb.ref = 1; r_bb.pool = 0; r_bb.w = 1920; r_bb.h = 1080;     /* (el backbuffer: del dispositivo, no cuenta) */
    r_rt[0] = &r_bb; r_bb.puesto = 1;
}

int main(void)
{
    printf("== el brillo: la mezcla ==\n");
    DWORD c, s, d;
    gr_brillo_mezcla(150, &c, &s, &d);
    chequear("150 → dst·1,5: DESTCOLOR / ONE con gris 0x7F", s == 9 && d == 2 && (c & 0xFF) == 127);
    gr_brillo_mezcla(50, &c, &s, &d);
    chequear("50 → dst·0,5: ZERO / SRCCOLOR con gris 0x7F", s == 1 && d == 3 && (c & 0xFF) == 127);
    gr_brillo_mezcla(113, &c, &s, &d);
    chequear("113 (el del dueño) → +13 %", s == 9 && (c & 0xFF) == 33);

    printf("== el filtrado en SetSamplerState ==\n");
    g_gr_sss_real = sss_falso;
    g_gr_aniso_ok = 1; g_gr_aniso_max = 16;
    g_gr_aniso = 8; g_gr_tri = 1; g_gr_nitidez = 0;
    memset(g_ss, 0, sizeof(g_ss));
    gr_sss(0, 0, 6, 2);
    chequear("MINFILTER LINEAR → ANISOTROPIC con MAXANISOTROPY 8", g_ss[6] == 3 && g_ss[10] == 8);
    gr_sss(0, 0, 6, 1);
    chequear("MINFILTER POINT (la interfaz pixelada) no se toca", g_ss[6] == 1);
    gr_sss(0, 0, 7, 1);
    chequear("MIPFILTER POINT → LINEAR (trilineal)", g_ss[7] == 2);
    gr_sss(0, 0, 7, 0);
    chequear("MIPFILTER NONE (sin mipmaps) no se toca", g_ss[7] == 0);
    gr_sss(0, 0, 10, 1);
    chequear("MAXANISOTROPY 1 del motor → 8", g_ss[10] == 8);
    g_gr_aniso_max = 4;
    gr_sss(0, 0, 6, 2);
    chequear("la placa puede 4×: pedido 8 → 4", g_ss[10] == 4);
    g_gr_aniso_ok = 0;
    g_ss[6] = 0;
    gr_sss(0, 0, 6, 2);
    chequear("sin anisotrópico en la placa: LINEAR queda LINEAR", g_ss[6] == 2);
    g_gr_aniso_ok = 1; g_gr_aniso_max = 16; g_gr_nitidez = 1;
    g_ss[8] = 0;
    gr_sss(0, 0, 6, 2);
    {
        float b; memcpy(&b, &g_ss[8], 4);
        chequear("nitidez: MIPMAPLODBIAS −0,5", b == -0.5f);
    }
    g_gr_aniso = 1; g_gr_tri = 0; g_gr_nitidez = 0;
    gr_sss(0, 0, 6, 2); gr_sss(0, 0, 7, 1); gr_sss(0, 0, 10, 1);
    chequear("perfil bajo: nada cambia (LINEAR, POINT, 1)", g_ss[6] == 2 && g_ss[7] == 1 && g_ss[10] == 1);

    printf("== el antialias ==\n");
    g_d3d_vt[11] = (void *)cms_falso;
    g_gr_d3d = &g_d3d_obj;
    DWORD pp[14] = {1920, 1080, 22, 1, 0, 0, 3, 0, 1, 1, 75, 1, 0, 0};
    g_gr_aa_max = 8; g_gr_aa = 4; g_aa_hw = 4;
    gr_ajustar_pp(pp);
    chequear("4× pedido y aceptado: MultiSampleType 4, DISCARD, sin LOCKABLE", pp[4] == 4 && pp[6] == 1 && !(pp[11] & 1));
    g_gr_aa = 8;
    gr_ajustar_pp(pp);
    chequear("8× pedido, la placa llega a 4× → 4×", pp[4] == 4 && g_gr_aa_puesto == 4);
    g_gr_aa = 0;
    gr_ajustar_pp(pp);
    chequear("apagado: MultiSampleType 0 (el de antes se borra)", pp[4] == 0 && g_gr_aa_puesto == 0);
    g_aa_hw = 0; g_gr_aa = 2;
    gr_ajustar_pp(pp);
    chequear("la placa no acepta nada: 0", pp[4] == 0);
    g_gr_aa_max = 2; g_gr_aa = 8; g_aa_hw = 8;
    chequear("tope de la placa 2×: pedido 8 → 2", gr_limitar_aa(g_gr_aa) == 2);

    printf("== los perfiles y el ini ==\n");
    g_ini_n = 0;
    gr_leer_ini("x");
    chequear("sin nada guardado: perfil alto (8×, trilineal, 2×, sombras 256)", g_gr_perfil == 2 && g_gr_aniso == 8 && g_gr_tri && g_gr_aa == 2 && g_gr_sombras_res == 256);
    chequear("sin nada guardado: el destello rojo QUITADO", g_gr_destello == 0);
    WritePrivateProfileStringA("graficos", "perfil", "bajo", "x");
    gr_leer_ini("x");
    chequear("perfil bajo: sin anisotrópico ni antialias ni sombras", g_gr_aniso == 1 && !g_gr_tri && g_gr_aa == 0);
    g_gr_perfil = 3; g_gr_aniso = 16; g_gr_tri = 1; g_gr_nitidez = 1; g_gr_aa = 4; g_gr_sombras_res = 512;
    gr_guardar_ini("x");
    g_gr_aniso = 0;
    gr_leer_ini("x");
    chequear("guardado y leído otra vez: máximo, 16×, 4×, sombras 512", g_gr_perfil == 3 && g_gr_aniso == 16 && g_gr_aa == 4 && g_gr_sombras_res == 512);
    WritePrivateProfileStringA("opciones", "brillo_pantalla", "113", "x");
    gr_leer_ini("x");
    chequear("el brillo guardado (113) llega al Present", g_gr_brillo == 113);
    WritePrivateProfileStringA("graficos", "antialias", "3", "x");
    gr_leer_ini("x");
    chequear("un antialias raro (3) → 0", g_gr_aa == 0);
    for (int k = 0; k < 4; k++)
        chequear("cada perfil: anisotrópico y antialias válidos, sube de a poco",
                 (GR_P[k].aniso == 1 || GR_P[k].aniso == 4 || GR_P[k].aniso == 8 || GR_P[k].aniso == 16) && gr_aa_valido(GR_P[k].aa)
                 && (k == 0 || GR_P[k].aniso >= GR_P[k - 1].aniso));

    printf("== Options → Pantalla: qué ventana entra ==\n");
    /* (bordes y título de Windows 10/11 a 100 %: ~16×39) */
    chequear("1600×900 entra en un 1080 (1920×1040 de trabajo)", pan_cabe(1600, 900, 16, 39, 1920, 1040));
    chequear("1920×1080 en ventana NO entra en un 1080", !pan_cabe(1920, 1080, 16, 39, 1920, 1040));
    chequear("1280×720 entra en un 1024×768 de trabajo 1024×728? no (es más ancho)", !pan_cabe(1280, 720, 16, 39, 1024, 728));
    chequear("2560×1440 entra en un 4K", pan_cabe(2560, 1440, 16, 39, 3840, 2100));
    printf("== las letras: el gemelo al doble ==\n");
    {
        /* un trazo vertical de 2 px (alfa 15) con borde 8 y ruido 1 alrededor */
        BYTE a4[8 * 8] = {0}, a8[16 * 16];
        for (int y = 0; y < 8; y++) { a4[y * 8 + 3] = 15; a4[y * 8 + 4] = 15; a4[y * 8 + 2] = 8; a4[y * 8 + 6] = 1; }
        gr_letras_escalar(a4, 8, 8, a8);
        chequear("el centro del trazo queda opaco", a8[8 * 16 + 7] > 240 && a8[8 * 16 + 8] > 240);
        chequear("el ruido de 1/15 desaparece (x 12..13)", a8[8 * 16 + 12] == 0 && a8[8 * 16 + 13] == 0);
        chequear("lo transparente lejos queda 0", a8[8 * 16 + 0] == 0 && a8[8 * 16 + 15] == 0);
        chequear("el borde a mitad (8/15) queda intermedio, sin escalones de 1/15", a8[8 * 16 + 4] > 60 && a8[8 * 16 + 4] < 220);
    }
    {
        /* texturas de mentira: GetType 10 · GetLevelCount 13 · GetLevelDesc 17 · LockRect 19 · UnlockRect 20 · AddRef 1 · Release 2 */
        printf("== las letras: qué textura es un atlas ==\n");
        static unsigned short px_letras[64 * 64], px_otra[64 * 64];
        for (int i = 0; i < 64 * 64; i++) { px_letras[i] = (unsigned short)(((i % 7) < 3 ? 0xF000 : 0) | 0x0FFF); px_otra[i] = (unsigned short)(0xF000 | (i & 0x0FFF)); }
        int r = gr_prueba_atlas(px_letras, px_otra);
        chequear("un A4R4G4B4 todo blanco con tinta → atlas de letras: gemelo 128×128 A8R8G8B8", r == 1);
        chequear("otra A4R4G4B4 con colores → no se toca", g_otra_cambiada == 0);
        chequear("SetTexture pone el gemelo en lugar del atlas (y la otra igual)", g_settex_ultima == g_gemelo_creado && g_settex_otra == g_tex_otra_ptr);
        static TEX t3d;
        static unsigned short px3d[64 * 64];
        for (int i = 0; i < 64 * 64; i++) px3d[i] = (unsigned short)(((i % 5) < 2 ? 0xF000 : 0) | 0x0FFF);
        t3d.vt = g_tex_vt; t3d.px = px3d; t3d.w = 64; t3d.h = 64; t3d.fmt = 26;
        g_e2d_es_orto = 0;                                   /* (la escena 3D: perspectiva) */
        int antes = g_gr_fu_n;
        gr_settex(g_dev_vt, 0, &t3d);
        chequear("una textura blanca usada en la escena 3D (partícula) no se toca", g_gr_fu_n == antes && g_settex_ultima == &t3d);
        g_e2d_es_orto = 1;
    }
    {
        printf("== los textos de color (TextOutW → su textura) ==\n");
        static DWORD px_txt[32 * 32];
        for (int i = 0; i < 32 * 32; i++) px_txt[i] = (i % 3) ? 0x00000000u : 0xFF20C0E0u;
        static TEX tt;
        tt.vt = g_tx_vt; tt.px = (unsigned short *)px_txt; tt.w = 32; tt.h = 32; tt.fmt = 21;
        memcpy(g_tx_vt, g_tex_vt, sizeof(g_tx_vt));
        g_tx_vt[19] = (void *)t_lock32; g_tx_vt[2] = (void *)t_rel; g_tx_vt[20] = (void *)t_unlock;
        g_gr_ctex_real = f_ctex_txt;
        g_dev_vt[23] = (void *)gr_ctex;
        g_txt_a_crear = &tt;
        g_gr_toutw_real = f_toutw;
        gr_textoutw(0, 0, 0, 0, 0);                          /* (el juego dibuja un texto) */
        void *nueva = NULL;
        gr_ctex(g_dev_vt, 32, 32, 1, 0, 21, 1, &nueva, 0);    /* (y crea su textura) */
        chequear("la textura creada justo después de TextOutW queda anotada como texto", g_gr_tx_n == 1 && g_gr_tx[0].tex == &tt);
        g_gem_hecho = 0;
        g_txt_a_crear = &g_gem;                              /* (el gemelo de 64×64) */
        g_gem.w = 64; g_gem.h = 64;
        g_e2d_es_orto = 1;
        gr_settex(g_dev_vt, 0, &tt);
        chequear("SetTexture del texto pone su gemelo al doble", g_settex_ultima == &g_gem && g_gem_hecho == 1);
        gr_settex(g_dev_vt, 0, &tt);
        chequear("la segunda vez no lo rehace", g_gem_hecho == 1);
        ((long (WINAPI *)(void *, UINT))g_tx_vt[20])(&tt, 0);  /* (el juego reescribe el texto: UnlockRect) */
        gr_settex(g_dev_vt, 0, &tt);
        chequear("si el juego lo reescribe (UnlockRect), el gemelo se rehace", g_gem_hecho == 2);
        g_txt_a_crear = NULL;
        void *otra = NULL;
        gr_ctex(g_dev_vt, 32, 32, 1, 0, 21, 1, &otra, 0);     /* (sin TextOutW antes: no es texto) */
        chequear("una textura sin TextOutW antes no es texto", g_gr_tx_n == 1);
        g_rel_cero = 1;
        ((ULONG (WINAPI *)(void *))g_tx_vt[2])(&tt);           /* (el juego la suelta) */
        chequear("si el juego suelta el texto, se va de la lista (y su gemelo)", g_gr_tx_n == 0);
    }
    {   /* ★ el atlas de letras del juego, redibujado al doble en el mismo lugar ×2 */
        BYTE tabla[3 * 0x28]; memset(tabla, 0, sizeof tabla);
        const int cajas[3][4] = {{0, 2, 5, 10}, {1, 3, 7, 11}, {0, 0, 4, 12}};
        const int pos[3][2] = {{1, 1}, {8, 1}, {1, 15}};      /* (x+1, y+1 en el atlas de 32×32) */
        for (int i = 0; i < 3; i++) {
            BYTE *e = tabla + i * 0x28; *(WORD *)e = (WORD)('a' + i);
            memcpy(g_caja['a' + i], cajas[i], sizeof cajas[i]);
            int *c = (int *)(e + 4); memcpy(c, cajas[i], sizeof cajas[i]);
            float *uv = (float *)(e + 0x18);
            uv[0] = (pos[i][0] + 0.5f) / 32; uv[1] = (pos[i][1] + 0.5f) / 32;
        }
        WORD *d = gr_atlas_doble((HDC)1, tabla, 3, 32, 32);
        chequear("el atlas se redibuja (64×64)", d != NULL && g_textos == 3);
        chequear("con la misma fuente al doble de alto", g_fuente_dc.lfHeight == -24);
        int bien = d != NULL, fuera = 0;
        for (int i = 0; d && i < 3; i++) {
            int gw = cajas[i][2] - cajas[i][0], gh = cajas[i][3] - cajas[i][1];
            for (int y = 0; y < gh * 2; y++) for (int x = 0; x < gw * 2; x++)
                if (d[(pos[i][1] * 2 + y) * 64 + pos[i][0] * 2 + x] != 0xFFFF) bien = 0;
        }
        for (int y = 0; d && y < 64; y++) for (int x = 0; x < 64; x++) {
            int dentro = 0;
            for (int i = 0; i < 3; i++) {
                int gw = cajas[i][2] - cajas[i][0], gh = cajas[i][3] - cajas[i][1];
                if (x >= pos[i][0] * 2 && x < (pos[i][0] + gw) * 2 && y >= pos[i][1] * 2 && y < (pos[i][1] + gh) * 2) dentro = 1;
            }
            if (!dentro && d[y * 64 + x] != 0x0FFF) fuera++;
        }
        chequear("cada letra queda en su lugar ×2, entera", bien);
        chequear("nada se sale de la caja de la letra (sin rayitas del vecino)", d && fuera == 0);
        free(d);
        g_fuente.lfQuality = 5;
        d = gr_atlas_doble((HDC)1, tabla, 3, 32, 32);
        chequear("ClearType se dibuja en gris (sin bordes de color)", d && g_fuente_dc.lfQuality == 4);
        free(d);
        chequear("un atlas sin letras o enorme no se toca", !gr_atlas_doble((HDC)1, tabla, 0, 32, 32) && !gr_atlas_doble((HDC)1, tabla, 3, 4096, 32));
        g_gr_letras = 1;
        void *otra2 = NULL; int n0 = g_gr_tx_n;
        g_gr_texto_hilo = GetCurrentThreadId();
        gr_ctex(g_dev_vt, 32, 32, 1, 0, 21, 1, &otra2, 0);
        chequear("con letras=1 los gemelos de prueba no se usan", g_gr_tx_n == n0);
    }
    {   /* ★ las fuentes del motor (CUIVectorFont): el atlas al doble, aparte, con la línea de base en su lugar */
        static BYTE marco[0x1700]; memset(marco, 0, sizeof marco);
        static const char letras_vf[] = "gA";
        *(int *)(marco + 0x18) = 2; *(int *)(marco + 0x50) = 12; *(int *)(marco + 0x5C) = 8;
        *(const char **)(marco + 0x16CC) = letras_vf;
        const int cg[4] = {4, 7, 1, 4}, ca[4] = {6, 8, 0, 8};      /* g: baja de la línea; A: apoyada */
        memcpy(g_vf_caja['g'], cg, sizeof cg); memcpy(g_vf_caja['A'], ca, sizeof ca);
        int *gm = (int *)(marco + 0x2C4);
        gm[0] = cg[0]; gm[1] = cg[1]; gm[2] = cg[2]; gm[3] = cg[3];
        gm[5] = ca[0]; gm[6] = ca[1]; gm[7] = ca[2]; gm[8] = ca[3];
        WORD tabla[6] = {6, 0, 0, 8, 6, 0};                           /* (ancho+2, x, y) */
        g_fuente.lfHeight = -12; g_fuente.lfQuality = 4;
        BYTE *a8 = gr_vf_doble((HDC)1, marco, tabla, 32, 16);
        chequear("la fuente del motor se redibuja al doble (64×32)", a8 != NULL && g_fuente_dc.lfHeight == -24);
        int bien = a8 != NULL, fuera = 0;
        for (int y = 0; a8 && y < 32; y++) for (int x = 0; x < 64; x++) {
            int g_in = x >= 0 && x < 8 && y >= 2 * (8 - 4) && y < 2 * (8 - 4) + 14;     /* g: x 0..2·4, filas 2·(asc−oy) +2·7 */
            int a_in = x >= 2 * 6 && x < 2 * 6 + 12 && y >= 0 && y < 16;               /* A: x 2·6.., filas 0..2·8 */
            int tinta = a8[y * 64 + x] == 255;
            if ((g_in || a_in) && !tinta) bien = 0;
            if (!(g_in || a_in) && a8[y * 64 + x]) fuera++;
        }
        chequear("cada letra en su lugar ×2, con la línea de base del motor (la g baja, la A apoyada)", bien);
        chequear("nada fuera de las letras", a8 && fuera == 0);
        WORD datos[32 * 16]; for (int i = 0; i < 32 * 16; i++) datos[i] = (WORD)(((i % 5) ? 0 : 0xF000) | 0x0FFF);
        free(a8);
        g_gr_letras = 1; g_gr_vf_n = 0;
        gr_vf_registrar((HDC)1, marco, tabla, datos, 32, 16);
        BYTE a4[32 * 16]; for (int i = 0; i < 32 * 16; i++) a4[i] = (BYTE)(datos[i] >> 12);
        chequear("el atlas queda anotado y se reconoce por sus letras", g_gr_vf_n == 1 && gr_vf_buscar(a4, 32, 16) == g_gr_vf[0].a8);
        a4[7] ^= 1;
        chequear("otro contenido o tamaño no se confunde", !gr_vf_buscar(a4, 32, 16) && !gr_vf_buscar(a4, 16, 32));
        *(int *)(marco + 0x50) = 0;
        chequear("si la pila no cuadra (alto 0), no se toca nada", !gr_vf_doble((HDC)1, marco, tabla, 32, 16));
    }
    {   /* ★ las rayitas: con una letra suelta puesta, CLAMP y lineal; después, lo que pidió el juego */
        printf("== las letras sueltas: CLAMP mientras se dibujan ==\n");
        M_SAMPLER viejo = g_gr_sss_real; g_gr_sss_real = sss_falso; memset(g_ss, 0, sizeof g_ss);
        g_gr_letras = 1; g_gr_aniso = 1;
        gr_sss(0, 0, 1, 1); gr_sss(0, 0, 2, 1); gr_sss(0, 0, 5, 1); gr_sss(0, 0, 6, 1);      /* (el juego: WRAP y punto) */
        gr_glifo_poner(0, 0, 1);
        chequear("una letra puesta: CLAMP en U y V, filtro lineal", g_ss[1] == 3 && g_ss[2] == 3 && g_ss[5] == 2 && g_ss[6] == 2);
        gr_sss(0, 0, 1, 1);
        chequear("si el juego pide WRAP con la letra puesta, queda CLAMP (y se anota)", g_ss[1] == 3 && g_gr_ss_juego[0][1] == 1);
        gr_glifo_poner(0, 0, 0);
        chequear("con otra textura vuelve lo del juego (WRAP y punto)", g_ss[1] == 1 && g_ss[2] == 1 && g_ss[5] == 1 && g_ss[6] == 1);
        gr_sss(0, 0, 7, 1);
        chequear("lo demás pasa como siempre", g_ss[7] == 1 || g_ss[7] == 2);
        printf("== (20-nov) la raya de «Shop|» / «Inventory»: imágenes de la interfaz con CLAMP, el filtro del juego ==\n");
        TEX img = {0};
        gr_sss(0, 0, 1, 1); gr_sss(0, 0, 2, 1); gr_sss(0, 0, 5, 2); gr_sss(0, 0, 6, 2);      /* (medido: WRAP + LINEAR) */
        g_e2d_es_orto = 1; g_e2d_activa = 1; g_gr_ui_clamp = 1;
        chequear("la rutina 2D del motor (0x77C7C5), escala activa, etapa 0: es imagen", gr_ui_es_imagen(&img, 0, 0, 0x0077C7C5u));
        chequear("otra rutina (escena, efectos): no", !gr_ui_es_imagen(&img, 0, 0, 0x006C9EDDu));
        chequear("otra etapa: no", !gr_ui_es_imagen(&img, 1, 0, 0x0077C7C5u));
        chequear("una letra: no (la maneja el arreglo de letras)", !gr_ui_es_imagen(&img, 0, 1, 0x0077C7C5u));
        g_e2d_activa = 0;
        chequear("a 800×600 (sin escala): no, queda como 2009", !gr_ui_es_imagen(&img, 0, 0, 0x0077C7C5u));
        g_e2d_activa = 1; g_e2d_es_orto = 0;
        chequear("en la escena 3D (perspectiva): no", !gr_ui_es_imagen(&img, 0, 0, 0x0077C7C5u));
        g_e2d_es_orto = 1; g_gr_ui_clamp = 0;
        chequear("[graficos] interfaz_clamp=0: no", !gr_ui_es_imagen(&img, 0, 0, 0x0077C7C5u));
        g_gr_ui_clamp = 1;
        gr_glifo_poner(0, 0, 2);
        chequear("imagen puesta: CLAMP en U y V, el filtro LINEAR del juego sigue", g_ss[1] == 3 && g_ss[2] == 3 && g_ss[5] == 2 && g_ss[6] == 2);
        gr_sss(0, 0, 1, 1); gr_sss(0, 0, 5, 1);
        chequear("con la imagen puesta: WRAP pedido queda CLAMP; un filtro pedido (POINT) sí pasa", g_ss[1] == 3 && g_ss[5] == 1);
        gr_sss(0, 0, 5, 2);
        gr_glifo_poner(0, 0, 1);
        chequear("de imagen a letra: CLAMP + LINEAR", g_ss[1] == 3 && g_ss[5] == 2 && g_ss[6] == 2);
        gr_glifo_poner(0, 0, 0);
        chequear("y con otra textura vuelve lo del juego (WRAP)", g_ss[1] == 1 && g_ss[2] == 1);
        g_gr_sss_real = viejo;
    }
    printf("== (20-nov) Reset tras un Stage: lo que quedó PUESTO se saca antes (si no, Reset → 0x8876086C) ==\n");
    {
        r_armar();
        void *dev = r_dev_vt; *(void ***)dev = r_dev_vt;
        void *settex_antes = (void *)g_gr_settex_real;
        g_gr_settex_real = NULL;
        /* lo que deja un Stage: el render target 1024×1024 (Capítulos / efecto) en la etapa 1, un búfer DEFAULT en el
         *   stream 0, una textura MANAGED en la etapa 0 y el render target como destino 0; sus dueños ya los soltaron */
        REC *rt = r_nuevo(r_tex_vt, 3, 0, 1, 1024, 1024), *vb = r_nuevo(r_vb_vt, 0, 0, 0x8, 96000, 0),
            *man = r_nuevo(r_tex_vt, 3, 1, 0, 256, 256), *rts = r_nuevo(r_sup_vt, 0, 0, 1, 1024, 1024);
        r_settex(dev, 1, rt); r_settex(dev, 0, man); r_setss(dev, 0, vb, 0, 32); r_setrt(dev, 0, rts);
        r_release(rt); r_release(vb); r_release(rts);
        chequear("sin sacar nada: Reset → 0x8876086C (como en el juego a las 01:24 y 01:32)", r_reset(dev, NULL) == (long)0x8876086C);
        char diag[400];
        int n = gr_reset_desligar(dev, NULL, NULL, diag, sizeof(diag));
        printf("    desligados del pool DEFAULT: %d ·%s\n", n, diag);
        chequear("cuenta los 3 del pool DEFAULT que estaban puestos (no la MANAGED)", n == 3);
        chequear("el diag dice cuáles (etapa 1 1024x1024, stream 0, destino 0)", strstr(diag, "etapa 1 1024x1024") && strstr(diag, "stream 0") && strstr(diag, "destino 0"));
        chequear("quedan sin poner: etapas, stream e índices; destino 0 = el backbuffer", !r_tex[0] && !r_tex[1] && !r_vb[0] && !r_ib && r_rt[0] == &r_bb);
        chequear("no suelta referencias de sus dueños (la MANAGED sigue con 1)", man->ref == 1 && rt->ref == 0 && vb->ref == 0);
        chequear("y AHORA el Reset anda", r_reset(dev, NULL) == 0);
        REC *vivo = r_nuevo(r_tex_vt, 3, 0, 1, 512, 512);           /* (uno que su dueño NO soltó: eso no se esconde) */
        r_settex(dev, 2, vivo);
        gr_reset_desligar(dev, NULL, NULL, NULL, 0);
        chequear("si el dueño todavía lo tiene, el Reset sigue fallando (no se tapa una pérdida de verdad)", r_reset(dev, NULL) == (long)0x8876086C && vivo->ref == 1);
        /* (20-nov, revisión) no sólo texturas: cubo, índices, destino 1 y profundidad propia; referencias equilibradas */
        r_release(vivo); r_settex(dev, 2, NULL);
        REC *cubo = r_nuevo(r_tex_vt, 5, 0, 1, 256, 256), *ib = r_nuevo(r_vb_vt, 0, 0, 0x8, 6000, 0),
            *rt1 = r_nuevo(r_sup_vt, 0, 0, 1, 512, 512), *ds = r_nuevo(r_sup_vt, 0, 0, 2, 1024, 1024),
            *suyo = r_nuevo(r_tex_vt, 3, 1, 0, 64, 64);
        r_settex(dev, 3, cubo); r_setib(dev, ib); r_setrt(dev, 1, rt1); r_setds(dev, ds); r_settex(dev, 4, suyo);
        r_release(cubo); r_release(ib); r_release(rt1); r_release(ds);
        int bb_ref = r_bb.ref;
        chequear("cubo + índices + destino 1 + profundidad puestos: Reset → 0x8876086C", r_reset(dev, NULL) == (long)0x8876086C);
        n = gr_reset_desligar(dev, NULL, NULL, diag, sizeof(diag));
        printf("    desligados del pool DEFAULT: %d ·%s\n", n, diag);
        chequear("los cuenta (cubo, índices, destino 1) y anota la profundidad", n == 3 && strstr(diag, "índices") && strstr(diag, "destino 1") && strstr(diag, "profundidad 1024x1024"));
        chequear("todo sin poner (también la profundidad y la etapa 4)", !r_tex[3] && !r_tex[4] && !r_ib && !r_rt[1] && !r_ds);
        chequear("referencias equilibradas: la del juego sigue (1), el backbuffer igual", suyo->ref == 1 && r_bb.ref == bb_ref && cubo->ref == 0 && ds->ref == 0);
        chequear("y el Reset anda", r_reset(dev, NULL) == 0);
        REC *rt_suyo = r_nuevo(r_sup_vt, 0, 0, 1, 256, 256);          /* (un destino que el juego TODAVÍA tiene) */
        r_setrt(dev, 1, rt_suyo);
        n = gr_reset_desligar(dev, NULL, NULL, diag, sizeof(diag));
        chequear("un destino que el juego todavía tiene: se saca pero NO se suelta (ref 1) → el Reset falla y se ve", rt_suyo->ref == 1 && r_reset(dev, NULL) == (long)0x8876086C);
        chequear("[graficos] reset_desligar viene en 1 (0 = como antes)", g_gr_desligar == 1);
        g_gr_settex_real = settex_antes;
    }
    printf("== las franjas con ambiente: qué parte de la imagen chica va en cada franja ==\n");
    {
        RECT izq = {0, 0, 240, 1080}, der = {1680, 0, 1920, 1080}, s;        /* 1920×1080: interfaz 1440×1080 en x 240 */
        gr_amb_fuente(&izq, 1920, 1080, 1440, 1080, 45, 33, &s);
        chequear("izquierda (1920×1080, chica 45×33): el borde izquierdo de la interfaz, x 0–6, una franja vertical del centro",
                 s.left == 0 && s.right == 6 && s.top > 0 && s.bottom < 33 && s.bottom - s.top >= 20);
        RECT s2;
        gr_amb_fuente(&der, 1920, 1080, 1440, 1080, 45, 33, &s2);
        chequear("★ el revés: la derecha es el espejo (x 39–45), no la misma parte que la izquierda",
                 s2.left == 39 && s2.right == 45 && s2.top == s.top && s2.bottom == s.bottom);
        RECT arriba = {0, 0, 1280, 64};                                       /* 1280×1024: interfaz 1280×960 en y 32 */
        gr_amb_fuente(&arriba, 1280, 1024, 1280, 960, 40, 30, &s);
        chequear("letterbox (1280×1024): la de arriba toma una franja horizontal de arriba", s.top == 0 && s.bottom >= 1 && s.right - s.left >= 30);
        RECT finita = {0, 0, 1, 1080};
        gr_amb_fuente(&finita, 1920, 1080, 1440, 1080, 45, 33, &s);
        chequear("una franja de 1 px: igual da al menos 1×1 dentro", s.right - s.left >= 1 && s.left >= 0 && s.right <= 45);
    }
    printf("prueba_graficos: %d bien · %d mal\n", ok, mal);
    return mal != 0;
}
