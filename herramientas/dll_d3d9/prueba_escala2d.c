/* prueba_escala2d.c — ★ (Punto 5) las pruebas de eda_escala2d.c sin Windows ni el juego: un «dispositivo» de mentira
 *   que anota lo que le llega, y las cuentas de la escala (proyección, viewport, scissor, RHW, mouse).
 *     gcc -std=gnu11 -o /tmp/pe herramientas/dll_d3d9/prueba_escala2d.c -lm && /tmp/pe */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* ── lo mínimo de Windows ── */
typedef unsigned long DWORD; typedef unsigned char BYTE; typedef unsigned int UINT; typedef long LONG;
typedef unsigned short WORD; typedef unsigned long ULONG; typedef unsigned long ULONG_PTR; typedef long LPARAM;
typedef void *HWND; typedef void *HANDLE; typedef int BOOL;
typedef struct { LONG left, top, right, bottom; } RECT;
typedef struct { LONG x, y; } POINT;
typedef struct { HWND hwnd; UINT message; unsigned long wParam; LPARAM lParam; } MSG;
#define WINAPI
#define WM_MOUSEFIRST 0x200
#define WM_MOUSEMOVE 0x200
#define WM_LBUTTONDOWN 0x201
#define WM_MOUSEWHEEL 0x20A
#define WM_MOUSELAST 0x20E
#define WM_KEYDOWN 0x100
#define LOWORD(l) ((WORD)((unsigned long)(l) & 0xFFFF))
#define HIWORD(l) ((WORD)(((unsigned long)(l) >> 16) & 0xFFFF))
#define MAKELPARAM(a, b) ((LPARAM)(((unsigned long)(WORD)(a)) | (((unsigned long)(WORD)(b)) << 16)))
#define InterlockedIncrement(p) (++*(p))
#define InterlockedDecrement(p) (--*(p))
#define VT(o) (*(void ***)(o))
static long InterlockedExchange(volatile long *p, long v) { long a = *p; *p = v; return a; }
static void *GetProcessHeap(void) { return 0; }
static void *HeapAlloc(void *h, int f, size_t n) { (void)h; (void)f; return malloc(n); }
static int HeapFree(void *h, int f, void *p) { (void)h; (void)f; free(p); return 1; }
static void lstrcpynA(char *d, const char *s, int n) { strncpy(d, s, n - 1); d[n - 1] = 0; }
static unsigned long g_tick = 1000;
static unsigned long GetTickCount(void) { return g_tick; }
#define MAX_PATH 260
/* un eda_d3d9.ini de mentira: [pantalla] clave=valor */
static char g_ini_k[32][32], g_ini_v[32][96];
static int g_ini_n;
static int ini_buscar(const char *k) { for (int i = 0; i < g_ini_n; i++) if (!strcmp(g_ini_k[i], k)) return i; return -1; }
static int WritePrivateProfileStringA(const char *a, const char *k, const char *v, const char *f)
{
    (void)a; (void)f;
    int i = ini_buscar(k);
    if (i < 0) { i = g_ini_n++; strcpy(g_ini_k[i], k); }
    strncpy(g_ini_v[i], v, 95);
    return 1;
}
static int GetPrivateProfileIntA(const char *a, const char *b, int d, const char *f) { (void)a; (void)f; int i = ini_buscar(b); return i < 0 ? d : atoi(g_ini_v[i]); }
static int GetPrivateProfileStringA(const char *a, const char *b, const char *d, char *o, int n, const char *f)
{ (void)a; (void)f; int i = ini_buscar(b); lstrcpynA(o, i < 0 ? d : g_ini_v[i], n); return 0; }
#define lstrcpyA strcpy
#define wsprintfA sprintf
static int GetEnvironmentVariableA(const char *n, char *o, int c) { (void)n; (void)o; (void)c; return 0; }
static int g_cli_w = 1920, g_cli_h = 1080;
static BOOL GetClientRect(HWND h, RECT *r) { (void)h; r->left = r->top = 0; r->right = g_cli_w; r->bottom = g_cli_h; return 1; }
static BOOL ClientToScreen(HWND h, POINT *p) { (void)h; p->x += 100; p->y += 50; return 1; }
static int g_apuntes;
static void apuntar(const char *fmt, ...) { (void)fmt; g_apuntes++; }
static BYTE *g_escena_vt;                                  /* la escena «actual» de mentira */
static int g_mira_juego, g_inactiva;
static POINT g_cur_fisico;
static BOOL __attribute__((stdcall)) cursor_falso(POINT *p) { *p = g_cur_fisico; return 1; }                        /* [0x917884] y [0x90DE80] de mentira */
static BYTE *leer_ptr(const void *p)
{
    if ((ULONG_PTR)p == 0x917884) return (BYTE *)(ULONG_PTR)g_mira_juego;
    if ((ULONG_PTR)p == 0x90DE80) return (BYTE *)(ULONG_PTR)g_inactiva;
    return (BYTE *)&g_escena_vt;
}
static int legible(const void *p, size_t n) { (void)p; (void)n; return 0; }
#define PAGE_EXECUTE_READWRITE 0x40
static int VirtualProtect(void *a, size_t n, DWORD p, DWORD *v) { (void)a; (void)n; (void)p; (void)v; return 0; }
static void poner(void **vt, int i, void *nuevo, void **viejo) { *viejo = vt[i]; vt[i] = nuevo; }
static HWND g_ventana_juego = (HWND)1;
static int g_medir5, g_res_w = 800, g_res_h = 600, g_diagnostico;
static void medir5_guardar(void *dev, DWORD escena) { (void)dev; (void)escena; }
static int g_entrada = 1;
#include "eda_escala2d.c"
static void rojo_dibujo(DWORD dir, int clase) { (void)dir; (void)clase; }
static void rojo_rhw(DWORD dir, DWORD fvf, const void *v, UINT n, UINT paso) { (void)dir; (void)fvf; (void)v; (void)n; (void)paso; }
static int entrada_ok(void) { return g_entrada; }

/* ── el dispositivo de mentira: anota lo último que le llegó ── */
static float d_proj[16]; static DWORD d_vp[6]; static RECT d_sc; static const void *d_vertices;
static long WINAPI f_st(void *d, DWORD t, const float *m) { (void)d; if (t == 3) memcpy(d_proj, m, sizeof(d_proj)); return 0; }
static long WINAPI f_gt(void *d, DWORD t, float *m) { (void)d; (void)t; memcpy(m, d_proj, sizeof(d_proj)); return 0; }
static long WINAPI f_vp(void *d, const DWORD *v) { (void)d; memcpy(d_vp, v, sizeof(d_vp)); return 0; }
static long WINAPI f_gvp(void *d, DWORD *v) { (void)d; memcpy(v, d_vp, sizeof(d_vp)); return 0; }
static long WINAPI f_sc(void *d, const RECT *r) { (void)d; d_sc = *r; return 0; }
static long WINAPI f_gsc(void *d, RECT *r) { (void)d; *r = d_sc; return 0; }
static long WINAPI f_dpup(void *d, DWORD t, UINT n, const void *v, UINT s) { (void)d; (void)t; (void)n; (void)s; d_vertices = v; return 0; }
static long WINAPI f_dipup(void *d, DWORD t, UINT a, UINT b, UINT c, const void *i, DWORD f, const void *v, UINT s)
{ (void)d; (void)t; (void)a; (void)b; (void)c; (void)i; (void)f; (void)s; d_vertices = v; return 0; }
static long WINAPI f_fvf(void *d, DWORD f) { (void)d; (void)f; return 0; }
static long WINAPI f_srt(void *d, DWORD i, void *s) { (void)d; (void)i; (void)s; return 0; }
/* una superficie de mentira: GetDesc (vt 12) da su tamaño */
typedef struct { void **vt; int w, h; } SUP;
static long WINAPI sup_desc(void *o, DWORD *d) { SUP *s = (SUP *)o; memset(d, 0, 32); d[0] = 21; d[6] = (DWORD)s->w; d[7] = (DWORD)s->h; return 0; }
static void *g_sup_vt[16];
static void *g_tabla[120];

static int ok, mal;
static void chequear(const char *n, int c) { printf("  %s %s\n", c ? "OK " : "MAL", n); if (c) ok++; else mal++; }
static int cerca(float a, float b, float tol) { return fabsf(a - b) <= tol; }

/* la ortográfica del juego (0x77B4F0): Scaling(1,−1,1) · Translation(−0.5, ...) · OrthoOffCenterLH(0,W,H,0,0,1) → en filas */
static void orto_juego(float *m, int w, int h)
{
    memset(m, 0, 16 * sizeof(float));
    m[0] = 2.0f / w; m[5] = -2.0f / h; m[10] = 1; m[12] = -1 - 1.0f / w; m[13] = 1 + 1.0f / h; m[15] = 1;
}
/* un punto de la interfaz por la proyección → píxel de la pantalla (con un viewport) */
static void a_pixel(const float *m, const DWORD *vp, float x, float y, float *px, float *py)
{
    float nx = x * m[0] + y * m[4] + m[12], ny = x * m[1] + y * m[5] + m[13];
    *px = vp[0] + (nx + 1) / 2 * vp[2];
    *py = vp[1] + (1 - ny) / 2 * vp[3];
}
static void perspectiva(float *m, float fx, float fy)
{
    memset(m, 0, 16 * sizeof(float));
    m[0] = 1 / tanf(fx / 2); m[5] = 1 / tanf(fy / 2); m[10] = 1.001f; m[11] = 1; m[14] = -0.1f;
}

int main(void)
{
    void *dev = g_tabla;
    void **vt = g_tabla;
    vt[44] = (void *)f_st; vt[45] = (void *)f_gt; vt[47] = (void *)f_vp; vt[48] = (void *)f_gvp; vt[75] = (void *)f_sc;
    vt[76] = (void *)f_gsc; vt[83] = (void *)f_dpup; vt[84] = (void *)f_dipup; vt[89] = (void *)f_fvf; vt[37] = (void *)f_srt;
    *(void ***)dev = vt;                                     /* (VT(dev) = la tabla) */
    vt = g_tabla;
    float m[16], px, py;
    DWORD vp_entero[6] = {0, 0, 1920, 1080, 0, 0x3F800000};

    printf("== apagada (escala2d=0): nada cambia ==\n");
    g_e2d = 0;
    DWORD pp[2] = {1920, 1080};
    e2d_dispositivo(vt, pp);
    chequear("sin escala2d no se engancha nada", vt[44] == (void *)f_st && !e2d_activa());
    g_e2d = 1;
    pp[0] = 800; pp[1] = 600;
    e2d_dispositivo(vt, pp);
    chequear("con escala2d a 800×600: enganchado pero inactiva (s = 1)", vt[44] == (void *)e2d_settransform && !e2d_activa());
    orto_juego(m, 800, 600);
    ((E2D_ST)vt[44])(dev, 3, m);
    chequear("a 800×600 la ortográfica pasa igual", !memcmp(d_proj, m, sizeof(m)));

    printf("== 1920×1080: la interfaz en R = 1440×1080, x 240 ==\n");
    pp[0] = 1920; pp[1] = 1080;
    e2d_dispositivo(vt, pp);
    chequear("activa · s 1,8 · R x 240 y 0", e2d_activa() && cerca(g_e2d_s, 1.8f, 1e-4f) && cerca(g_e2d_rx, 240, 0.01f)
             && cerca(g_e2d_ry, 0, 0.01f));
    g_escena_vt = (BYTE *)0x00899F10;                        /* inventario */
    g_e2d_stage_ahora = 0;
    ((E2D_VP)vt[47])(dev, vp_entero);
    orto_juego(m, 1920, 1080);
    ((E2D_ST)vt[44])(dev, 3, m);
    a_pixel(d_proj, d_vp, 0, 0, &px, &py);
    chequear("esquina (0,0) de la interfaz → (240, 0) (± medio píxel)", cerca(px, 240 - 0.5f, 0.6f) && cerca(py, 0 - 0.5f, 0.6f));
    a_pixel(d_proj, d_vp, 800, 600, &px, &py);
    chequear("esquina (800,600) → (1680, 1080)", cerca(px, 1680 - 0.5f, 0.6f) && cerca(py, 1080 - 0.5f, 0.6f));
    a_pixel(d_proj, d_vp, 578, 39, &px, &py);
    chequear("el botón Options (578,39) → (1280, 70): escala uniforme ×1,8", cerca(px, 240 + 578 * 1.8f - 0.5f, 0.6f)
             && cerca(py, 39 * 1.8f - 0.5f, 0.6f));
    chequear("el viewport de la interfaz queda entero (la proyección hace la escala)", !memcmp(d_vp, vp_entero, sizeof(d_vp)));
    float g[16];
    ((E2D_GT)vt[45])(dev, 3, g);
    chequear("GetTransform devuelve la del juego, no la cambiada", !memcmp(g, m, sizeof(m)));

    printf("== la cámara del personaje (perspectiva fuera del Stage) ==\n");
    float rad = 3.14159265f / 180;
    perspectiva(m, 70 * rad, 70 * rad * 1080 / 1920);     /* la regla del juego: FovY = FovX · H/W */
    ((E2D_ST)vt[44])(dev, 3, m);
    chequear("su viewport de pantalla entera → R (240, 0, 1440×1080)", d_vp[0] == 240 && d_vp[1] == 0 && d_vp[2] == 1440 && d_vp[3] == 1080);
    float fy = 2 * atanf(1 / d_proj[5]) / rad;
    chequear("FovY como a 800×600 (70 × 600/800 = 52,5°), FovX igual", cerca(fy, 52.5f, 0.05f) && d_proj[0] == m[0]);
    chequear("k medido = 1 (la regla del juego)", cerca(g_e2d_k, 1, 0.01f));
    DWORD gv[6];
    ((E2D_GVP)vt[48])(dev, gv);
    chequear("GetViewport devuelve el del juego", !memcmp(gv, vp_entero, sizeof(gv)));
    orto_juego(m, 1920, 1080);
    ((E2D_ST)vt[44])(dev, 3, m);
    chequear("después, la interfaz vuelve al viewport entero", !memcmp(d_vp, vp_entero, sizeof(d_vp)));

    printf("== el Stage: 3D nativo, HUD escalado ==\n");
    g_e2d_stage_ahora = 1;
    perspectiva(m, 70 * rad, 70 * rad * 1080 / 1920);
    ((E2D_ST)vt[44])(dev, 3, m);
    chequear("la perspectiva del Stage NO se toca", !memcmp(d_proj, m, sizeof(m)) && !memcmp(d_vp, vp_entero, sizeof(d_vp)));
    orto_juego(m, 1920, 1080);
    ((E2D_ST)vt[44])(dev, 3, m);
    a_pixel(d_proj, d_vp, 0, 0, &px, &py);
    chequear("el HUD del Stage sí va a R (escala2d_stage=1)", cerca(px, 239.5f, 0.6f));
    g_e2d_stage = 0;
    ((E2D_ST)vt[44])(dev, 3, m);
    chequear("con escala2d_stage=0 el HUD queda como hoy", !memcmp(d_proj, m, sizeof(m)));
    MSG ms = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(591, 42)};
    e2d_mouse(&ms);
    chequear("…y el mouse tampoco se convierte en el Stage", (short)LOWORD(ms.lParam) == 591);
    g_e2d_stage = 1;
    g_e2d_stage_ahora = 0;

    printf("== una parte de la interfaz (viewport / scissor de una lista) ==\n");
    float o2[16];
    memset(o2, 0, sizeof(o2));
    o2[0] = 2.0f / 200; o2[5] = -2.0f / 100; o2[10] = 1; o2[12] = -1; o2[13] = 1; o2[15] = 1;
    DWORD vp_parte[6] = {100, 50, 200, 100, 0, 0x3F800000};
    ((E2D_VP)vt[47])(dev, vp_parte);
    ((E2D_ST)vt[44])(dev, 3, o2);
    chequear("viewport (100,50 200×100) → (420, 90, 360×180)", d_vp[0] == 420 && d_vp[1] == 90 && d_vp[2] == 360 && d_vp[3] == 180);
    chequear("su ortográfica no se toca (la escala la da el viewport)", !memcmp(d_proj, o2, sizeof(o2)));
    RECT sc = {100, 50, 300, 150};
    ((E2D_SC)vt[75])(dev, &sc);
    chequear("scissor (100,50)-(300,150) → (420,90)-(780,270)", d_sc.left == 420 && d_sc.top == 90 && d_sc.right == 780 && d_sc.bottom == 270);
    RECT gs;
    ((E2D_GSC)vt[76])(dev, &gs);
    chequear("GetScissorRect devuelve el del juego", gs.left == 100 && gs.bottom == 150);
    RECT entero = {0, 0, 1920, 1080};
    ((E2D_SC)vt[75])(dev, &entero);
    chequear("un scissor de pantalla entera no se toca", d_sc.right == 1920 && d_sc.left == 0);

    printf("== dibujos XYZRHW ==\n");
    ((E2D_FVF)vt[89])(dev, 0x144);                           /* XYZRHW | DIFFUSE | TEX1 */
    float q[3][7] = {{10, 20, 0, 1, 0, 0, 0}, {790, 20, 0, 1, 0, 1, 0}, {10, 590, 0, 1, 0, 0, 1}};
    ((E2D_DPUP)vt[83])(dev, 4, 1, q, sizeof(q[0]));
    const float *r = (const float *)d_vertices;
    chequear("RHW de la interfaz → R (10,20 → 258,36)", r != &q[0][0] && cerca(r[0], 258, 0.01f) && cerca(r[1], 36, 0.01f)
             && cerca(r[7], 240 + 790 * 1.8f, 0.01f) && q[0][0] == 10);
    float pant[3][7] = {{0, 0, 0, 1, 0, 0, 0}, {1920, 0, 0, 1, 0, 1, 0}, {0, 1080, 0, 1, 0, 0, 1}};
    ((E2D_DPUP)vt[83])(dev, 4, 1, pant, sizeof(pant[0]));
    chequear("RHW de pantalla entera (un efecto) → igual", d_vertices == pant);
    ((E2D_DIPUP)vt[84])(dev, 4, 0, 3, 1, NULL, 101, q, sizeof(q[0]));
    r = (const float *)d_vertices;
    chequear("DrawIndexedPrimitiveUP RHW de la interfaz → R", r != &q[0][0] && cerca(r[0], 258, 0.01f));
    ((E2D_FVF)vt[89])(dev, 0x142);                           /* XYZ: va por la proyección */
    ((E2D_DPUP)vt[83])(dev, 4, 1, q, sizeof(q[0]));
    chequear("un dibujo XYZ no se toca acá", d_vertices == q);
    g_e2d_propio = 1;
    ((E2D_FVF)vt[89])(dev, 0x044);
    ((E2D_DPUP)vt[83])(dev, 4, 1, q, sizeof(q[0]));
    chequear("lo que dibuja la dll (el contador) no se toca", d_vertices == q);
    g_e2d_propio = 0;

    printf("== el mouse ==\n");
    MSG mm = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(1280, 70)};
    e2d_mouse(&mm);
    chequear("ventana (1280,70) → interfaz (578,39): el botón Options", (short)LOWORD(mm.lParam) == 578 && (short)HIWORD(mm.lParam) == 39);
    MSG mi = {(HWND)1, WM_LBUTTONDOWN, 0, MAKELPARAM(100, 500)};
    e2d_mouse(&mi);
    chequear("en la franja negra izquierda → x negativa (fuera de la interfaz)", (short)LOWORD(mi.lParam) < 0);
    MSG rueda = {(HWND)1, WM_MOUSEWHEEL, 0, MAKELPARAM(1280, 70)};
    e2d_mouse(&rueda);
    chequear("la rueda (coordenadas de pantalla) no se toca", (short)LOWORD(rueda.lParam) == 1280);
    MSG tecla = {(HWND)1, WM_KEYDOWN, 0, 0x12345};
    e2d_mouse(&tecla);
    chequear("el teclado no se toca", tecla.lParam == 0x12345);
    int ida = 0, vuelta = 0, x, y;
    for (int vx = 240; vx < 1680; vx += 37)
        for (int vy = 0; vy < 1080; vy += 41) {
            x = vx; y = vy;
            e2d_ventana_a_ui(NULL, &x, &y);
            e2d_ui_a_ventana(NULL, &x, &y);
            ida++;
            if (abs(x - vx) <= 1 && abs(y - vy) <= 1) vuelta++;
        }
    chequear("ida y vuelta ventana → interfaz → ventana (±1 px) en toda R", ida == vuelta);
    g_cli_h = 1071;                                          /* (Windows achicó la ventana 9 px) */
    mm.lParam = MAKELPARAM(1280, 70 * 1071 / 1080);
    e2d_mouse(&mm);
    chequear("con el cliente 1920×1071 (Windows estira) sigue en el botón", abs((short)HIWORD(mm.lParam) - 39) <= 1);
    g_cli_h = 1080;
    int cx = 100 + 578, cy = 50 + 39;                        /* el juego pone el cursor en SU (578,39) + el origen */
    e2d_setcur(&cx, &cy, 0x780BE1);
    chequear("SetPhysicalCursorPos: interfaz (578,39) → pantalla (100+1280, 50+70)", cx == 100 + 1280 && cy == 50 + 70);

    printf("== el Stage: apuntar según el juego ([0x917884]) y el centrado por su dirección de vuelta ==\n");
    g_e2d_stage_ahora = 1;
    g_mira_juego = 1;
    cx = 100 + 960; cy = 50 + 540;                           /* el centrado del bucle (vuelve a 0x40B13B) */
    e2d_setcur(&cx, &cy, 0x40B13B);
    chequear("el centrado del bucle va TAL CUAL (no al borde: 1968)", cx == 100 + 960 && cy == 50 + 540 && c_e2d_mirada == 1);
    cx = 100 + 957; cy = 50 + 514;                           /* en modo ventana sale corrido por la barra de título */
    e2d_setcur(&cx, &cy, 0x40B13B);
    chequear("el centrado en modo ventana (957,514): también tal cual", cx == 100 + 957 && cy == 50 + 514 && c_e2d_mirada == 2);
    MSG ap = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(972, 514)};
    e2d_mouse(&ap);
    chequear("apuntando: el juego recibe (400,300) + el movimiento real (+15,0), como a 800×600",
             (short)LOWORD(ap.lParam) == 415 && (short)HIWORD(ap.lParam) == 300);
    MSG quieto = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(957, 514)};
    e2d_mouse(&quieto);
    chequear("apuntando, el mouse en el centro: (400,300) exacto (la cámara no se mueve sola)",
             (short)LOWORD(quieto.lParam) == 400 && (short)HIWORD(quieto.lParam) == 300);
    chequear("(diag) movimiento real 15 · convertido habría sido ~8 (×1/1,8)", g_e2d_mov_real == 15 && g_e2d_mov_ui >= 8 && g_e2d_mov_ui <= 9);
    g_inactiva = 1;
    MSG fuera_app = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(1280, 70)};
    e2d_mouse(&fuera_app);
    chequear("con la aplicación inactiva (el juego no centra) se convierte", (short)LOWORD(fuera_app.lParam) == 578);
    g_inactiva = 0;
    printf("== REWARD CHOICE / AWARD RESULTS: misma escena 0x899C20, el juego NO centra y mueve el cursor por la interfaz ==\n");
    g_mira_juego = 0;
    cx = 100 + 318; cy = 50 + 215;                           /* (13:18:25: el juego puso el cursor en SU (318,215)) */
    e2d_setcur(&cx, &cy, 0x780BE1);
    chequear("su «poner el cursor» (vuelve a 0x780BE1) es interfaz: (318,215) → pantalla (812,387)",
             cx == 100 + 812 && cy == 50 + 387 && c_e2d_mirada == 2);
    MSG carta = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(1280, 70)};
    e2d_mouse(&carta);
    chequear("y el mouse se convierte a la interfaz (no «(400,300)+movimiento»)", (short)LOWORD(carta.lParam) == 578);
    MSG clic = {(HWND)1, WM_LBUTTONDOWN, 0, MAKELPARAM(812, 387)};
    e2d_mouse(&clic);
    chequear("el clic cae donde está el cursor: (812,387) → (318,215)",
             (short)LOWORD(clic.lParam) == 318 && (short)HIWORD(clic.lParam) == 215);
    chequear("después de un «poner el cursor» de la interfaz, el centro guardado está en píxeles de la ventana (812,387)",
             g_e2d_cur_x == 812 && g_e2d_cur_y == 387);
    g_mira_juego = 1;                                        /* (14:55:20 del dueño: «centro (400,300)» → salto +557,+214) */
    MSG vuelve = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(812, 387)};
    e2d_mouse(&vuelve);
    chequear("vuelve a apuntar con el mouse donde lo dejó el juego: (400,300), sin salto",
             (short)LOWORD(vuelve.lParam) == 400 && (short)HIWORD(vuelve.lParam) == 300);
    g_mira_juego = 0;
    g_e2d_stage_ahora = 0;
    cx = 100 + 400; cy = 50 + 300;
    e2d_setcur(&cx, &cy, 0x780BE1);
    chequear("fuera del Stage un SetPhysicalCursorPos es interfaz y se convierte", cx == 100 + 960 && cy == 50 + 540 && c_e2d_mirada == 2);
    MSG fuera = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(975, 532)};
    e2d_mouse(&fuera);
    chequear("fuera del Stage el mouse se convierte", (short)LOWORD(fuera.lParam) == 408);

    printf("== GetPhysicalCursorPos del juego (0x780CD0 al volver el foco): las mismas coordenadas que los mensajes ==\n");
    g_e2d_getcur_real = cursor_falso;
    g_cur_fisico.x = 100 + 957; g_cur_fisico.y = 50 + 514;    /* el mouse físico en el centro que puso el juego */
    g_e2d_stage_ahora = 1; g_mira_juego = 1; g_e2d_cur_x = 957; g_e2d_cur_y = 514;
    POINT pc;
    e2d_getcur(&pc);
    chequear("apuntando, el mouse en el centro → el juego lee (400,300): la cámara no salta (antes leía 957,514)",
             pc.x == 100 + 400 && pc.y == 50 + 300);
    g_cur_fisico.x = 100 + 967;
    e2d_getcur(&pc);
    chequear("apuntando, 10 px a la derecha → (410,300)", pc.x == 100 + 410 && pc.y == 50 + 300);
    g_entrada = 0; g_cur_fisico.x = 100 + 1498; g_cur_fisico.y = 50 + 167;   /* Options abierta, el mouse en su X */
    e2d_getcur(&pc);
    chequear("apuntando con Options abierta (mouse en su X, 1498,167) → (400,300): la cámara no se mueve (antes 941,-47)",
             pc.x == 100 + 400 && pc.y == 50 + 300);
    g_entrada = 1; g_cur_fisico.x = 100 + 967; g_cur_fisico.y = 50 + 514;
    g_mira_juego = 0;
    g_cur_fisico.x = 100 + 1280; g_cur_fisico.y = 50 + 70;
    e2d_getcur(&pc);
    chequear("sin apuntar → la posición en la interfaz (1280,70) → (578,39)", pc.x == 100 + 578 && pc.y == 50 + 39);
    g_e2d_stage_ahora = 0;
    e2d_di_mouse(5, -3);
    chequear("(diag) el mouse de DirectInput sólo se cuenta en el Stage", c_e2d_di == 0);
    g_e2d_stage_ahora = 1;
    e2d_di_mouse(5, -3);
    chequear("(diag) en el Stage sí: |x| 5, |y| 3", c_e2d_di == 1 && g_e2d_di_x == 5 && g_e2d_di_y == 3);
    g_e2d_stage_ahora = 0;

    printf("== otra resolución: 1280×720 y 2560×1080 (ultra ancha) ==\n");
    pp[0] = 1280; pp[1] = 720;
    e2d_dispositivo(NULL, pp);
    chequear("1280×720 → s 1,2 · R 960×720 en x 160", cerca(g_e2d_s, 1.2f, 1e-4f) && cerca(g_e2d_rx, 160, 0.01f));
    pp[0] = 2560; pp[1] = 1080;
    e2d_dispositivo(NULL, pp);
    chequear("2560×1080 → s 1,8 · R en x 560", cerca(g_e2d_s, 1.8f, 1e-4f) && cerca(g_e2d_rx, 560, 0.01f));
    pp[0] = 1024; pp[1] = 1280;                              /* (vertical: manda el ancho) */
    e2d_dispositivo(NULL, pp);
    chequear("1024×1280 → s 1,28 · centrado en y", cerca(g_e2d_s, 1.28f, 1e-4f) && cerca(g_e2d_ry, 256, 0.01f) && cerca(g_e2d_rx, 0, 0.01f));

    printf("== resultados por la fase del Stage (escena+0x248 ≥ 5), aunque «apuntar» vuelva a 1 ==\n");
    pp[0] = 1920; pp[1] = 1080;
    e2d_dispositivo(NULL, pp);
    g_e2d_stage_ahora = 1; g_mira_juego = 1; g_inactiva = 0;
    g_e2d_res_fase = 0;
    chequear("jugando (fase 4) y apuntar 1 → apunta", e2d_apuntando());
    g_e2d_res_fase = 1;
    chequear("REWARD (fase 7) con apuntar 1 (14:56:23 del dueño) → NO apunta", !e2d_apuntando());
    g_e2d_cur_x = 957; g_e2d_cur_y = 514;
    MSG en_carta = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(1280, 70)};
    e2d_mouse(&en_carta);
    chequear("y el mouse va a la interfaz (1280,70) → (578,39)", (short)LOWORD(en_carta.lParam) == 578 && (short)HIWORD(en_carta.lParam) == 39);
    g_e2d_res_fase = 0; g_mira_juego = 0; g_e2d_stage_ahora = 0;

    printf("== resolución desde Options: confirmar y volver atrás ==\n");
    g_ini_n = 0;
    WritePrivateProfileStringA("pantalla", "escala2d", "1", "x");
    WritePrivateProfileStringA("pantalla", "resolucion", "1920x1080", "x");
    WritePrivateProfileStringA("pantalla", "resolucion_anterior", "1280x720", "x");
    WritePrivateProfileStringA("pantalla", "escala2d_anterior", "1", "x");
    WritePrivateProfileStringA("pantalla", "confirmar", "1", "x");
    g_res_w = 800; g_res_h = 600; g_medir5 = 0;
    e2d_leer_ini("x");
    chequear("primer intento: arranca con 1920×1080 y anota intentos=1", g_res_w == 1920 && g_res_h == 1080
             && GetPrivateProfileIntA("pantalla", "intentos", 0, "x") == 1 && g_e2d_confirmar_pend);
    g_res_w = 800; g_res_h = 600; g_e2d_confirmar_pend = 0;
    e2d_leer_ini("x");                                       /* (el intento anterior nunca se confirmó) */
    chequear("segundo arranque sin confirmar → vuelve a 1280×720 y lo avisa", g_res_w == 1280 && g_res_h == 720
             && GetPrivateProfileIntA("pantalla", "confirmar", 1, "x") == 0 && g_e2d_revertida[0]);
    WritePrivateProfileStringA("pantalla", "resolucion", "1920x1080", "x");
    WritePrivateProfileStringA("pantalla", "confirmar", "1", "x");
    WritePrivateProfileStringA("pantalla", "intentos", "0", "x");
    g_res_w = 800; g_res_h = 600;
    e2d_leer_ini("x");
    g_tick = 50000;
    e2d_confirmar();                                         /* (empieza a contar: hay escena) */
    g_tick = 59000;
    e2d_confirmar();
    chequear("8 s dibujando una escena → confirmada (confirmar=0, intentos=0)", !g_e2d_confirmar_pend
             && GetPrivateProfileIntA("pantalla", "confirmar", 1, "x") == 0 && GetPrivateProfileIntA("pantalla", "intentos", 1, "x") == 0);
    WritePrivateProfileStringA("pantalla", "escala2d", "0", "x");
    g_res_w = 800; g_res_h = 600;
    e2d_leer_ini("x");
    chequear("(Punto 6) escala2d=0 en el ini ya no la apaga: la resolución se aplica y la adaptación 2D sigue", g_res_w == 1920 && g_e2d);
    g_res_w = 800; g_res_h = 600;

    printf("== resolución en vivo: la pantalla entera de antes y el mouse que estira ==\n");
    g_e2d = 1;
    g_e2d_propio = 0;
    g_e2d_stage_ahora = 0;
    e2d_tamano(1920, 1080, "prueba");
    {
        DWORD viejo[6] = {0, 0, 1280, 720, 0, 0x3F800000}, parte[6] = {10, 10, 1280, 720, 0, 0x3F800000};
        g_e2d_tipo = 1;
        ((E2D_VP)vt[47])(dev, viejo);
        chequear("sin cambio en vivo, (0,0) 1280×720 queda como está", d_vp[2] == 1280 && d_vp[3] == 720);
        e2d_viejo_agregar(1280, 720);
        ((E2D_VP)vt[47])(dev, viejo);
        chequear("tras el cambio en vivo, (0,0) 1280×720 (la pantalla de antes) → 1920×1080", d_vp[2] == 1920 && d_vp[3] == 1080);
        ((E2D_VP)vt[47])(dev, parte);
        chequear("un viewport que no empieza en (0,0) no se toca", d_vp[0] == 10 && d_vp[2] == 1280);
        e2d_tamano(1280, 720, "prueba");
        ((E2D_VP)vt[47])(dev, viejo);
        chequear("si 1280×720 vuelve a ser el backbuffer, ya no es «viejo»", d_vp[2] == 1280 && d_vp[3] == 720);
        float q[4][7] = {{0, 0, 0, 1, 0, 0, 0}, {1920, 0, 0, 1, 0, 0, 0}, {0, 1080, 0, 1, 0, 0, 0}, {1920, 1080, 0, 1, 0, 0, 0}};
        e2d_viejo_agregar(1920, 1080);
        g_e2d_fvf = 0x144;
        const float *r = (const float *)e2d_rhw(q, 4, 28);
        chequear("un XYZRHW de pantalla entera de antes (1920×1080) → la de ahora (1280×720)", r != (const float *)q && cerca(r[7], 1280, 0.01f) && cerca(r[15], 720, 0.01f));
        g_e2d_viejos_n = 0;
    }
    e2d_tamano(800, 600, "prueba");
    g_cli_w = 1920; g_cli_h = 1080;
    {
        MSG est = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(960, 540)};
        e2d_mouse(&est);
        chequear("800×600 sin bordes (ventana 1920×1080): el mouse va a 400,300", (short)LOWORD(est.lParam) == 400 && (short)HIWORD(est.lParam) == 300);
        g_cli_w = 800; g_cli_h = 600;
        MSG igual = {(HWND)1, WM_MOUSEMOVE, 0, MAKELPARAM(123, 45)};
        e2d_mouse(&igual);
        chequear("800×600 en ventana de 800×600: el mouse no se toca", (short)LOWORD(igual.lParam) == 123);
    }
    printf("== (Punto 6b) dibujar en una TEXTURA (Capítulos/Misiones): se mira, y la escala sigue IGUAL que en la pantalla ==\n");
    {
        g_sup_vt[12] = (void *)sup_desc;
        SUP pantalla = {g_sup_vt, 1920, 1080}, textura = {g_sup_vt, 1024, 1024};
        g_e2d_viejos_n = 0;
        g_e2d_propio = 0;
        g_e2d_stage = 1;
        g_e2d_stage_ahora = 1;
        e2d_tamano(1920, 1080, "prueba");
        g_e2d = 1;
        e2d_dispositivo(vt, NULL);                           /* (engancha SetRenderTarget) */
        typedef long (WINAPI *E2D_SRT)(void *, DWORD, void *);
        typedef long (WINAPI *E2D_STT)(void *, DWORD, const float *);
        float orto_tex[16];
        orto_juego(orto_tex, 1024, 1024);                    /* (una ortográfica que no es la de la pantalla) */
        DWORD vp_tex[6] = {0, 0, 512, 512, 0, 0x3F800000};
        ((E2D_SRT)vt[37])(dev, 0, &textura);
        chequear("SetRenderTarget a una textura 1024×1024: «fuera de la pantalla»", g_e2d_rt_fuera == 1);
        ((E2D_STT)vt[44])(dev, 3, orto_tex);
        ((E2D_VP)vt[47])(dev, vp_tex);
        DWORD vp_en_tex[6]; memcpy(vp_en_tex, d_vp, sizeof vp_en_tex);
        chequear("en la textura el viewport parcial se escala igual que en la pantalla (como d617fb02)", memcmp(d_vp, vp_tex, 16) != 0);
        ((E2D_SRT)vt[37])(dev, 0, &pantalla);
        chequear("de vuelta a la pantalla: «en la pantalla»", g_e2d_rt_fuera == 0);
        ((E2D_STT)vt[44])(dev, 3, orto_tex);
        ((E2D_VP)vt[47])(dev, vp_tex);
        chequear("en la pantalla, el mismo viewport parcial da lo mismo que en la textura", !memcmp(d_vp, vp_en_tex, 16));
        ((E2D_SRT)vt[37])(dev, 0, &textura);
        e2d_dispositivo(NULL, NULL);
        chequear("un Reset deja el destino en la pantalla", g_e2d_rt_fuera == 0);
    }
    printf("== (20-nov) cambio de resolución EN VIVO después de un Stage: queda para el reinicio ==\n");
    {
        int fv = g_e2d_fase_v, st = g_e2d_stages;
        g_e2d_fase_v = -1; g_e2d_stages = 0;
        chequear("al arrancar (lobby, sin Stage) el cambio en vivo vale", !e2d_vivo_bloqueado(0));
        e2d_fase_nueva(-1);
        chequear("fase -1 → -1 (sigue en el lobby): ningún Stage", g_e2d_stages == 0 && !e2d_vivo_bloqueado(0));
        e2d_fase_nueva(0);
        chequear("entrar al Stage (fase -1 → 0) cuenta 1", g_e2d_stages == 1 && g_e2d_fase_v == 0);
        chequear("dentro del Stage ya no se cambia en vivo", e2d_vivo_bloqueado(0));
        e2d_fase_nueva(4); e2d_fase_nueva(7);
        chequear("jugando y resultados (4, 7) no cuentan otro Stage", g_e2d_stages == 1);
        e2d_fase_nueva(-1);
        chequear("de vuelta en el lobby / Shop (01:32 del dueño): bloqueado → reinicio", e2d_vivo_bloqueado(0) && g_e2d_fase_v == -1);
        chequear("[pantalla] en_vivo_tras_stage=1 lo permite", !e2d_vivo_bloqueado(1));
        e2d_fase_nueva(2); e2d_fase_nueva(-1);
        chequear("otro Stage cuenta 2", g_e2d_stages == 2);
        chequear("(2) con en_vivo_tras_stage=1 se intenta en vivo tras un Stage", e2d_tras_stage_al_arrancar(1, 0) == 1);
        chequear("(2) si la sesión anterior se cerró en el intento → protección (0)", e2d_tras_stage_al_arrancar(1, 1) == 0);
        chequear("(2) con la protección elegida a mano sigue la protección", e2d_tras_stage_al_arrancar(0, 0) == 0);
        g_e2d_fase_v = fv; g_e2d_stages = st;
    }
    printf("prueba_escala2d: %d bien · %d mal\n", ok, mal);
    return mal ? 1 : 0;
}
