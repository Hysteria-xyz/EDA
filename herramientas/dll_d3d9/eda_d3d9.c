/* eda_d3d9.c — el d3d9.dll PROPIO de EDA: tope de cuadros + contador de cuadros en pantalla.
 *
 * Va AL LADO de EDA_limpio.exe / EDA.exe. Windows la carga antes que el d3d9 del sistema (el juego
 * la pide por nombre), así que se mete en el medio sin tocar un byte del juego. Reenvía todo al
 * d3d9 de verdad y engancha dos métodos del dispositivo:
 *
 *   · Present (17): ★ el TOPE DE CUADROS. EDA pide PresentationInterval IMMEDIATE y no tiene tope:
 *     dibuja ~900 cuadros/s en la lista de servidores y pone cualquier placa a máxima potencia;
 *     con dos juegos abiertos se pelean la placa y el que pierde cae a ~25 cuadros/s, y como el
 *     juego lee la red UNA vez por cuadro, el ping de la sala sube a ~75 ms (MEDICIONES §40–41).
 *     Con un tope de 120: placa en 48–84 W y ping de sala 8 ms (medido con DXVK). Acá el tope es
 *     NUESTRO (sin Vulkan: anda en cualquier PC con D3D9).
 *     Y, si se pide, dibuja arriba a la izquierda «FPS 120» con rectángulos (como un reloj digital:
 *     sin fuentes ni texturas).
 *   · Reset (16): suelta el «state block» del contador antes de que el juego resetee (si no, Reset
 *     falla), y lo vuelve a crear después.
 *
 * Ajustes: eda_d3d9.ini al lado de la dll —
 *     [video]
 *     tope_fps=120      ; 0 = sin tope
 *     mostrar_fps=1     ; 1 = el contador arriba a la izquierda
 * (las variables EDA_TOPE_FPS / EDA_MOSTRAR_FPS, si están, mandan: sirven para medir).
 * Registro: eda_d3d9.log al lado de la dll.
 *
 * Se compila con `py herramientas\dll_d3d9\compilar.py` (Zig, la misma receta que la de R2Beat).
 */
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VT(o) (*(void ***)(o))             /* la vtable de un objeto COM */
static void apuntar(const char *fmt, ...);

/* ── el d3d9 de verdad ─────────────────────────────────────────────────── */
typedef void *(WINAPI *CREAR9)(UINT);
static HMODULE g_real;
static CREAR9 g_crear;

/* ── ajustes ───────────────────────────────────────────────────────────── */
static int g_tope = 120;
static int g_mostrar = 1;
/* ★ backbuffer_rapido=1: en el CreateDevice/Reset del juego, sacar LOCKABLE_BACKBUFFER (Flags bit 1) y
 *   pasar SwapEffect COPY (3) → DISCARD (1). Lo mismo que hizo la dll de R2Beat («COPY prohíbe el
 *   camino rápido»). A medir en la SALA, que es donde el juego cae a ~15 cuadros/s. */
static int g_rapido = 0;
/* ★★★ buferes_rapidos=1 (MEDICIONES §42): EL CULPABLE DEL «LAG». En cada dibujo el juego bloquea su
 *   búfer de vértices ENTERO (96.000 B, POOL_DEFAULT, WRITEONLY, FVF 0x142) con Lock(0, 0, …, flags 0):
 *   ~290 veces por cuadro en la sala, y cada una hace esperar al procesador hasta que la placa termine
 *   de usar ese búfer. Con dos juegos las esperas se suman y los dos caen a ~14 cuadros/s.
 *   La salida: crear esos búferes DYNAMIC y convertir cada Lock(0, 0, 0) en Lock(…, DISCARD) — «dame
 *   uno nuevo, lo escribo entero» —: la placa sigue con el anterior sin parar. El juego siempre escribe
 *   desde el principio lo que va a dibujar, así que el dibujo es el mismo. */
static int g_buferes = 0;   /* ⚠ 12-nov: APAGADO por defecto ([video] anillo_vertices=1 lo prende; ver abajo) */
/* ★ [general] mejoras=0: la dll NO toca el video ni la red del juego (el juego como en 2009). Sigue
 *   haciendo sólo lo imprescindible: llevar el juego al server ([red] / el launcher), el login y la caja negra. */
static int g_mejoras = 1;
static long g_convertidos;

typedef long (WINAPI *M_CVB)(void *, UINT, DWORD, DWORD, DWORD, void **, void *);
typedef long (WINAPI *M_LOCK)(void *, UINT, UINT, void **, DWORD);
typedef long (WINAPI *M_DESC)(void *, void *);
static M_CVB g_cvb_real;
static M_LOCK g_lock_real;
typedef long (WINAPI *M_UNLOCK)(void *);
static M_UNLOCK g_unlock_real;

/* ★★ LA COPIA (11-nov): con DISCARD a secas se rompía la puerta del primer mapa — el juego bloquea el
 *   búfer ENTERO pero reescribe sólo una parte y cuenta con que el resto SIGA ahí; DISCARD lo borra.
 *   Ahora cada búfer «caliente» tiene una COPIA en memoria del procesador: el Lock del juego recibe la
 *   copia (con todo lo que había) y, en el Unlock, la dll pide un búfer nuevo a la placa (DISCARD:
 *   sin esperar) y le vuelca la copia ENTERA. Mismo resultado que el juego espera, sin frenar la placa. */
/* ★★★ EL ANILLO (11-nov, la versión buena). Medido con EDA_MEDIR_ESCRITURA: cada Lock del juego escribe
 *   DESDE EL PRINCIPIO del búfer ~100 B (un cuadradito), y a veces 38 KB de una (el escenario), que después
 *   se dibujan en varias veces entre medio de los cuadraditos. Con DISCARD a secas se perdía lo de 38 KB
 *   (la puerta rota); volcando la copia ENTERA en cada Unlock la placa volvía a 153 W.
 *   Ahora: el juego escribe en la COPIA (memoria del procesador) y la dll sube a la placa SÓLO lo que
 *   cada dibujo usa (el dibujo dice qué vértices), en el próximo lugar libre del búfer (NOOVERWRITE: sin
 *   esperar); cuando se llena, DISCARD y de nuevo desde el principio. Al dibujo se le corre el «vértice
 *   base» para que lea de ahí. Así se sube ~100 B por dibujo, la placa nunca espera y no se pierde nada. */
typedef struct { void *vb; UINT tam; BYTE *copia; int abierto, cargada; UINT anillo; } SOMBRA;

/* (medición, EDA_MEDIR_ESCRITURA=1): qué pedazo del búfer cambia en cada Lock/Unlock */
static int g_medir_escritura;
static BYTE *g_antes;
static UINT g_antes_tam;
static long g_med_n, g_med_desde0, g_med_bytes, g_med_max;
static UINT g_med_ultimo_fin;
static long g_med_siguiente;     /* cuántas veces el pedazo empieza donde terminó el anterior */
static SOMBRA g_sombras[32];

static SOMBRA *sombra_de(void *vb, UINT tam, int crear)
{
    SOMBRA *libre = NULL;
    for (int i = 0; i < 32; i++) {
        if (g_sombras[i].vb == vb) {
            if (g_sombras[i].tam == tam) return &g_sombras[i];
            HeapFree(GetProcessHeap(), 0, g_sombras[i].copia);   /* otro búfer en la misma dirección */
            g_sombras[i].vb = NULL;
        }
        if (!g_sombras[i].vb && !libre) libre = &g_sombras[i];
    }
    if (!crear || !libre) return NULL;
    libre->copia = (BYTE *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, tam);
    if (!libre->copia) return NULL;
    libre->vb = vb;
    libre->tam = tam;
    libre->abierto = 0;
    libre->cargada = 0;
    return libre;
}

/* ★ (15-nov) EL ANILLO, SÓLO PARA EL BÚFER MEDIDO. §42 midió UN culpable del «lag»: el búfer de vértices de
 *   96.000 B, FVF 0x142 (XYZ · color · 1 textura), POOL_DEFAULT, bloqueado entero ~290 veces por cuadro. Pero el
 *   anillo se aplicaba a TODOS los búferes POOL_DEFAULT del juego (los de la stage nunca se midieron), y en la
 *   stage dejó de dibujarse la interfaz (habilidades, ítems, ESC). Ahora sólo esos búferes se crean DYNAMIC y
 *   pasan por el anillo; los demás quedan como en 2009. Los demás búferes se anotan una vez (para medir). */
static void *g_candidatos[16];
static int g_es_candidato(void *vb)
{
    for (int i = 0; i < 16; i++) if (g_candidatos[i] == vb) return 1;
    return 0;
}
static void anotar_candidato(void *vb, int si)
{
    for (int i = 0; i < 16; i++) if (g_candidatos[i] == vb) g_candidatos[i] = NULL;
    if (!si) return;
    for (int i = 0; i < 16; i++) if (!g_candidatos[i]) { g_candidatos[i] = vb; return; }
}

static long WINAPI mi_lock(void *vb, UINT desde, UINT cuanto, void **datos, DWORD flags)
{
    if (g_buferes && g_es_candidato(vb)) {
        DWORD d[6] = {0};                                        /* D3DVERTEXBUFFER_DESC */
        if (((M_DESC)VT(vb)[13])(vb, d) == 0 && (d[2] & 0x200 /* DYNAMIC */)) {
            if (flags == 0 && desde == 0 && cuanto == 0) {
                SOMBRA *s = sombra_de(vb, d[4], 1);
                if (s && datos) {
                    if (!s->cargada) {
                        /* la 1ª vez, la copia arranca con lo que tiene el búfer */
                        void *p;
                        if (g_lock_real(vb, 0, 0, &p, 0x10 /* READONLY */) == 0) {
                            CopyMemory(s->copia, p, s->tam);
                            g_unlock_real(vb);
                        }
                        s->cargada = 1;
                    }
                    s->abierto = 1;
                    if (g_medir_escritura) {                     /* (foto de la copia antes de escribir) */
                        if (g_antes_tam != s->tam) {
                            g_antes = (BYTE *)HeapAlloc(GetProcessHeap(), 0, s->tam);
                            g_antes_tam = g_antes ? s->tam : 0;
                        }
                        if (g_antes) CopyMemory(g_antes, s->copia, s->tam);
                    }
                    *datos = s->copia;
                    g_convertidos++;
                    return 0;                                    /* D3D_OK: el juego escribe la copia */
                }
            } else {
                /* un Lock parcial sobre un búfer con copia: la placa no tiene la copia entera (sólo lo
                 *   que se fue dibujando): se vuelca toda una vez y se deja de usar la copia */
                SOMBRA *s = sombra_de(vb, d[4], 0);
                if (s && !s->abierto) {
                    void *p;
                    if (g_lock_real(vb, 0, 0, &p, 0x2000 /* DISCARD */) == 0) {
                        CopyMemory(p, s->copia, s->tam);
                        g_unlock_real(vb);
                    }
                    HeapFree(GetProcessHeap(), 0, s->copia);
                    s->vb = NULL;
                }
            }
        }
    }
    return g_lock_real(vb, desde, cuanto, datos, flags);
}

static long WINAPI mi_unlock(void *vb)
{
    for (int i = 0; i < 32; i++) {
        SOMBRA *s = &g_sombras[i];
        if (s->vb == vb && s->abierto) {
            s->abierto = 0;
            if (g_medir_escritura && g_antes && g_antes_tam == s->tam) {
                UINT a = 0, b = s->tam;
                while (a < s->tam && g_antes[a] == s->copia[a]) a++;
                while (b > a && g_antes[b - 1] == s->copia[b - 1]) b--;
                if (b > a) {
                    g_med_n++;
                    g_med_bytes += b - a;
                    if ((long)(b - a) > g_med_max) g_med_max = b - a;
                    if (a < 64) g_med_desde0++;
                    if (a >= g_med_ultimo_fin && a <= g_med_ultimo_fin + 64) g_med_siguiente++;
                    g_med_ultimo_fin = b;
                }
                if (g_med_n && g_med_n % 20000 == 0)
                    apuntar("  escritura: %ld bloqueos · promedio %ld B · máx %ld · empiezan en 0: %ld · siguen al anterior: %ld",
                            g_med_n, g_med_bytes / g_med_n, g_med_max, g_med_desde0, g_med_siguiente);
            }
            return 0;                       /* ★ nada se sube acá: se sube lo que use cada dibujo */
        }
    }
    return g_unlock_real(vb);
}

/* ── los dibujos: subir del anillo lo que usan ─────────────────────────── */
typedef long (WINAPI *M_SSS)(void *, UINT, void *, UINT, UINT);          /* SetStreamSource */
typedef long (WINAPI *M_DP)(void *, DWORD, UINT, UINT);                   /* DrawPrimitive */
typedef long (WINAPI *M_DIP)(void *, DWORD, INT, UINT, UINT, UINT, UINT); /* DrawIndexedPrimitive */
static M_SSS g_sss_real;
static M_DP g_dp_real;
static M_DIP g_dip_real;
static void *g_st_vb;                 /* lo puesto en el stream 0 */
static UINT g_st_desde, g_st_paso;
static long g_subidos, g_subidos_bytes;

static long WINAPI mi_sss(void *dev, UINT n, void *vb, UINT desde, UINT paso)
{
    if (n == 0) {
        g_st_vb = vb;
        g_st_desde = desde;
        g_st_paso = paso;
    }
    return g_sss_real(dev, n, vb, desde, paso);
}

/* sube [lo, lo+largo) de la copia al próximo lugar del anillo; devuelve cuántos VÉRTICES hay que correr
 *   el dibujo, o un número enorme si no se pudo (y entonces se sube TODO como antes) */
#define NO_SE_PUDO 0x7FFFFFFF
static int subir(SOMBRA *s, UINT lo, UINT largo, UINT paso)
{
    if (!paso || lo + largo > s->tam || largo == 0) return NO_SE_PUDO;
    UINT base = ((s->anillo + paso - 1) / paso) * paso;
    UINT p = base + (lo % paso);
    DWORD flags = 0x1000;                                        /* NOOVERWRITE: sin esperar */
    if (p + largo > s->tam) {
        p = lo % paso;                                           /* lleno: de nuevo desde el principio */
        flags = 0x2000;                                          /* DISCARD */
    }
    void *dst;
    if (g_lock_real(s->vb, p, largo, &dst, flags) != 0) return NO_SE_PUDO;
    CopyMemory(dst, s->copia + lo, largo);
    g_unlock_real(s->vb);
    s->anillo = p + largo;
    g_subidos++;
    g_subidos_bytes += largo;
    return (int)((INT)(p - lo) / (INT)paso);
}

/* ★ (15-nov) LA INTERFAZ QUE DESAPARECÍA EN LA STAGE (barra de habilidades, ítems, ventanas, ESC): el anillo
 *   sabía qué búfer estaba puesto sólo por SetStreamSource. Pero un «state block» (Apply: lo usan D3DX para
 *   dibujar los sprites 2D y el juego para guardar/restaurar estados) vuelve a poner el búfer del juego SIN pasar
 *   por SetStreamSource: el anillo creía que seguía el otro, no corría el dibujo y la placa leía el búfer VIEJO
 *   (sólo tiene lo que el anillo fue subiendo en otros lugares) → esos dibujos salían vacíos. Ahora, en cada
 *   dibujo, se le PREGUNTA al dispositivo (GetStreamSource) qué tiene puesto. g_desfasadas cuenta las veces que
 *   lo anotado no coincidía (si es > 0, era esto). */
typedef long (WINAPI *M_GSS)(void *, UINT, void **, UINT *, UINT *);       /* GetStreamSource (101) */
typedef ULONG (WINAPI *M_RELEASE)(void *);
static long g_desfasadas;
static SOMBRA *sombra_puesta(void *dev)
{
    void *vb = NULL;
    UINT desde = 0, paso = 0;
    if (dev && ((M_GSS)VT(dev)[101])(dev, 0, &vb, &desde, &paso) == 0) {
        if (vb) ((M_RELEASE)VT(vb)[2])(vb);                    /* (GetStreamSource le suma una referencia) */
        if (vb != g_st_vb || desde != g_st_desde || (vb && paso != g_st_paso)) g_desfasadas++;
        g_st_vb = vb;
        g_st_desde = desde;
        g_st_paso = paso;
    }
    if (!g_st_vb) return NULL;
    for (int i = 0; i < 32; i++)
        if (g_sombras[i].vb == g_st_vb && g_sombras[i].copia) return &g_sombras[i];
    return NULL;
}

static UINT vertices_de(DWORD tipo, UINT prims)
{
    switch (tipo) {
    case 1: return prims;            /* POINTLIST */
    case 2: return prims * 2;        /* LINELIST */
    case 3: return prims + 1;        /* LINESTRIP */
    case 4: return prims * 3;        /* TRIANGLELIST */
    case 5: case 6: return prims + 2;/* TRIANGLESTRIP / FAN */
    default: return 0;
    }
}

static void subir_todo(SOMBRA *s)
{
    void *p;
    if (g_lock_real(s->vb, 0, 0, &p, 0x2000) == 0) {
        CopyMemory(p, s->copia, s->tam);
        g_unlock_real(s->vb);
    }
    s->anillo = s->tam;              /* lo próximo, con DISCARD */
}

/* ★ (15-nov, PRUEBA A/B EN VIVO) Ctrl+F8 apaga el anillo en plena partida: cada búfer con copia se sube ENTERO a
 *   la placa (lo que el juego espera ver) y se suelta la copia; desde ahí Lock y dibujos pasan derecho. Si la barra
 *   de habilidades / ítems / ESC aparece al apretarlo, era el anillo. Ctrl+F8 otra vez lo vuelve a prender. */
static void anillo_en_vivo(int prender)
{
    if (!prender) {
        int n = 0;
        for (int i = 0; i < 32; i++) {
            SOMBRA *s = &g_sombras[i];
            if (s->vb && s->copia && !s->abierto) {
                subir_todo(s);
                HeapFree(GetProcessHeap(), 0, s->copia);
                s->copia = NULL;
                s->vb = NULL;
                n++;
            }
        }
        g_buferes = 0;
        apuntar("  ★ anillo APAGADO en vivo (Ctrl+F8): %d búferes devueltos enteros a la placa", n);
    } else if (g_lock_real) {
        g_buferes = 1;
        apuntar("  ★ anillo PRENDIDO en vivo (Ctrl+F8)");
    }
}

/* (15-nov, MEDIR) en la stage dejaron de salir las líneas de cuadros/s: ¿dibuja sin pasar por nuestro Present?
 *   Se cuentan los dibujos y, si pasan 5 s sin Present, se anota UNA vez (con cuántos dibujos y el dispositivo). */
static volatile DWORD g_ultimo_present;
static long g_dibujos_sin_present;
static int g_avisado_sin_present;
static void contar_dibujo(void *dev)
{
    g_dibujos_sin_present++;
    if (g_ultimo_present && !g_avisado_sin_present && (g_dibujos_sin_present & 1023) == 0
        && GetTickCount() - g_ultimo_present > 5000) {
        g_avisado_sin_present = 1;
        apuntar("  ⚠ (medir) %ld dibujos sin Present en 5 s · dispositivo 0x%08lX · anillo %d", g_dibujos_sin_present,
                (unsigned long)(ULONG_PTR)dev, g_buferes);
    }
}

static long WINAPI mi_dp(void *dev, DWORD tipo, UINT inicio, UINT prims)
{
    contar_dibujo(dev);
    SOMBRA *s = sombra_puesta(dev);
    if (s) {
        UINT n = vertices_de(tipo, prims);
        int corre = subir(s, g_st_desde + inicio * g_st_paso, n * g_st_paso, g_st_paso);
        if (corre != NO_SE_PUDO && (INT)inicio + corre >= 0)
            return g_dp_real(dev, tipo, (UINT)((INT)inicio + corre), prims);
        subir_todo(s);
    }
    return g_dp_real(dev, tipo, inicio, prims);
}

static long WINAPI mi_dip(void *dev, DWORD tipo, INT base, UINT minimo, UINT n, UINT desde_idx, UINT prims)
{
    contar_dibujo(dev);
    SOMBRA *s = sombra_puesta(dev);
    if (s) {
        INT primero = base + (INT)minimo;
        if (primero >= 0 && n > 0) {                     /* (n = 0: el juego no dijo cuántos → todo) */
            int corre = subir(s, g_st_desde + (UINT)primero * g_st_paso, n * g_st_paso, g_st_paso);
            if (corre != NO_SE_PUDO)
                return g_dip_real(dev, tipo, base + corre, minimo, n, desde_idx, prims);
        }
        subir_todo(s);
    }
    return g_dip_real(dev, tipo, base, minimo, n, desde_idx, prims);
}

static void poner(void **vt, int i, void *nuevo, void **viejo);

static long WINAPI mi_crear_vb(void *dev, UINT largo, DWORD uso, DWORD fvf, DWORD pool, void **vb, void *comp)
{
    int candidato = g_buferes && pool == 0 /* DEFAULT */ && fvf == 0x142 && largo == 96000;
    if (candidato && !(uso & 0x200)) uso |= 0x200;                             /* + DYNAMIC, sólo éste */
    long hr = g_cvb_real(dev, largo, uso, fvf, pool, vb, comp);
    if (hr == 0 && vb && *vb) {
        anotar_candidato(*vb, candidato);
        static int anotados;
        if (pool == 0 && anotados < 24) {
            anotados++;
            apuntar("  (medir) búfer de vértices POOL_DEFAULT: %u B · FVF 0x%lX · uso 0x%lX → %s", largo,
                    (unsigned long)fvf, (unsigned long)uso, candidato ? "ANILLO" : "como en 2009");
        }
    }
    if (hr == 0 && vb && *vb)                                  /* un búfer nuevo no hereda una copia vieja */
        for (int i = 0; i < 32; i++)
            if (g_sombras[i].vb == *vb && !g_sombras[i].abierto) {
                HeapFree(GetProcessHeap(), 0, g_sombras[i].copia);
                g_sombras[i].vb = NULL;
                g_sombras[i].copia = NULL;
            }
    if (hr == 0 && vb && *vb && !g_lock_real) {
        poner(VT(*vb), 12, (void *)mi_unlock, (void **)&g_unlock_real);
        poner(VT(*vb), 11, (void *)mi_lock, (void **)&g_lock_real);
        apuntar("  enganchados VertexBuffer::Lock/Unlock (búferes rápidos: copia + DISCARD)");
    }
    return hr;
}

static void ajustar_pp(void *pp)
{
    if (!g_rapido || !pp) return;
    DWORD *p = (DWORD *)pp;
    p[11] &= ~1u;                       /* +0x2C Flags: sin D3DPRESENTFLAG_LOCKABLE_BACKBUFFER */
    if (p[6] == 3) p[6] = 1;            /* +0x18 SwapEffect: COPY → DISCARD */
}
static char g_log[MAX_PATH];

static void apuntar(const char *fmt, ...)
{
    if (!g_log[0]) return;
    FILE *f = fopen(g_log, "a");
    if (!f) return;
    SYSTEMTIME t;
    GetLocalTime(&t);
    fprintf(f, "%02d:%02d:%02d.%03d  ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
    va_list a;
    va_start(a, fmt);
    vfprintf(f, fmt, a);
    va_end(a);
    fputc('\n', f);
    fclose(f);
}

/* ── los métodos del dispositivo que usamos (índices de IDirect3DDevice9) ── */
typedef long (WINAPI *M_PRESENT)(void *, const RECT *, const RECT *, HWND, const void *);
typedef long (WINAPI *M_RESET)(void *, void *);
typedef long (WINAPI *M_SIN)(void *);                                  /* BeginScene / EndScene */
typedef long (WINAPI *M_RS)(void *, DWORD, DWORD);                     /* SetRenderState, SetFVF… */
typedef long (WINAPI *M_TSS)(void *, DWORD, DWORD, DWORD);             /* SetTextureStageState */
typedef long (WINAPI *M_PTR)(void *, DWORD, void *);                   /* SetTexture */
typedef long (WINAPI *M_UNO)(void *, void *);                          /* SetVertex/PixelShader */
typedef long (WINAPI *M_DPUP)(void *, DWORD, UINT, const void *, UINT);
typedef long (WINAPI *M_CSB)(void *, DWORD, void **);                  /* CreateStateBlock */
typedef long (WINAPI *M_SB)(void *);                                   /* Capture / Apply / Release */
typedef long (WINAPI *M_CREARDEV)(void *, UINT, DWORD, HWND, DWORD, void *, void **);

enum { I_RESET = 16, I_PRESENT = 17, I_BEGINSCENE = 41, I_ENDSCENE = 42, I_SETRS = 57,
       I_CREATESB = 59, I_SETTEXTURE = 65, I_SETTSS = 67, I_DPUP = 83, I_SETFVF = 89,
       I_SETVS = 92, I_SETPS = 107 };

static M_PRESENT g_present_real;
static M_RESET g_reset_real;
static M_CREARDEV g_creardev_real;
static void *g_bloque;          /* el state block del contador (D3DSBT_ALL) */
static void *g_bloque_dev;      /* …y el dispositivo al que pertenece */

/* ── el reloj ──────────────────────────────────────────────────────────── */
static LARGE_INTEGER g_frec, g_proximo, g_ventana;
static int g_cuadros, g_fps;

static double ms_entre(LARGE_INTEGER a, LARGE_INTEGER b)
{
    return (double)(b.QuadPart - a.QuadPart) * 1000.0 / (double)g_frec.QuadPart;
}

/* ★★ LA RED NO ESPERA AL CUADRO (MEDICIONES §42). El juego lee su UDP una vez por vuelta del bucle,
 *   o sea una vez por cuadro: con el tope de 120 cada mensaje esperaba hasta 8 ms (ping de sala 8);
 *   a 480, 2. Eso está mal hecho de fábrica: la latencia no tiene que depender de los cuadros.
 *   El juego registra cada socket con WSAEventSelect(socket, EVENTO, FD_READ…): Windows levanta ese
 *   evento cuando llega algo. La dll se queda con los eventos de los sockets UDP y, en vez de dormir a
 *   ciegas entre cuadro y cuadro, ESPERA ESOS EVENTOS: si llega un mensaje, suelta al juego en el acto
 *   (un cuadro antes de hora) y lo lee enseguida. El tope sigue (la placa descansa) y la red, al toque. */
static int g_red = 1;                       /* [video] red_inmediata */
static int g_estricto = 1;                  /* [video] tope_estricto: los cuadros, FIJOS en el tope */
static HANDLE g_eventos[16];
static int g_neventos;
static long g_despertadas, g_bombeos;
typedef int (WSAAPI *M_WSAES)(SOCKET, WSAEVENT, long);
static M_WSAES g_wsaes_real;

/* ★★ EL BOMBEO DE RED DEL JUEGO (medido 11-nov, MEDICIONES §42): `0x74D530` es el método «actualizar»
 *   del socket UDP (thiscall, this = el objeto del socket, que es GLOBAL: 0x948F90): mira SIN esperar si
 *   el evento del socket (+0xAC) está levantado, y si lo está llama a `0x750110` (WSAEnumNetworkEvents
 *   → leer); después manda lo que tenga en cola. El juego lo llama UNA vez por cuadro, desde el hilo
 *   principal — el mismo del Present. Llamándolo NOSOTROS mientras esperamos el turno del cuadro, el
 *   juego atiende la red al instante SIN dibujar un cuadro de más: el tope queda fijo.
 *   ⚠ Antes de usarlo se verifican sus bytes y que el objeto tenga el socket (+0x88) y el evento
 *   (+0xAC) que el juego registró: con otro exe, no se llama a nada. */
typedef int (__attribute__((thiscall)) *M_BOMBEO)(void *);
static M_BOMBEO g_bombeo;
static void *g_socket_obj;
static HANDLE g_ev_bombeo;
/* ⛔ APAGADO por defecto ([video] bombeo_red=1 para experimentar): medido el 11-nov, apenas el juego
 *   lo usó en la sala (1, después 12 bombeos) LOS DOS JUEGOS SE CONGELARON. Llamar a 0x74D530 desde
 *   adentro del Present traba algo del juego (🟡 ¿un candado que tiene tomado mientras dibuja?). */
static int g_usar_bombeo = 0;
static const BYTE FIRMA_BOMBEO[12] = {0x53, 0x55, 0x8B, 0x2D, 0x74, 0xA1, 0x88, 0x00, 0x56, 0x8B, 0xF1, 0x57};
static const BYTE FIRMA_EVENTO[8] = {0x83, 0xEC, 0x2C, 0x56, 0x8B, 0xF1, 0x8B, 0x8E};

static int legible(const void *p, SIZE_T n)
{
    MEMORY_BASIC_INFORMATION m;
    if (!VirtualQuery(p, &m, sizeof(m)) || m.State != MEM_COMMIT || (m.Protect & (PAGE_NOACCESS | PAGE_GUARD)))
        return 0;
    return (const BYTE *)p + n <= (const BYTE *)m.BaseAddress + m.RegionSize;
}

static void buscar_bombeo(SOCKET s, WSAEVENT ev)
{
    BYTE *bombeo = (BYTE *)0x74D530, *evento = (BYTE *)0x750110, *obj = (BYTE *)0x948F90;
    if (!legible(bombeo, 12) || memcmp(bombeo, FIRMA_BOMBEO, 12) || !legible(evento, 8)
            || memcmp(evento, FIRMA_EVENTO, 8)) {
        apuntar("  ⚠ el bombeo de red no está donde lo esperaba (¿otro exe?): no se usa");
        return;
    }
    if (!legible(obj + 0x88, 0x28) || *(SOCKET *)(obj + 0x88) != s || *(HANDLE *)(obj + 0xAC) != ev) {
        apuntar("  (el socket %u no es el del objeto 0x948F90: no se bombea)", (unsigned)s);
        return;
    }
    g_bombeo = (M_BOMBEO)bombeo;
    g_socket_obj = obj;
    g_ev_bombeo = ev;
    apuntar("  ★ bombeo de red: 0x74D530 con el objeto 0x948F90 (socket %u, evento %p)", (unsigned)s, ev);
}

static int WSAAPI mi_wsa_event_select(SOCKET s, WSAEVENT ev, long que)
{
    int r = g_wsaes_real(s, ev, que);              /* ⚠ primero el real: el objeto ya tiene sus campos */
    int tipo = 0, largo = sizeof(tipo);
    if (ev && (que & FD_READ) && getsockopt(s, SOL_SOCKET, SO_TYPE, (char *)&tipo, &largo) == 0
            && tipo == SOCK_DGRAM) {
        int ya = 0;
        for (int i = 0; i < g_neventos; i++) ya |= g_eventos[i] == ev;
        if (!ya && g_neventos < 16) {
            g_eventos[g_neventos++] = ev;
            apuntar("  red inmediata: el socket UDP %u avisa con el evento %p", (unsigned)s, ev);
            if (!g_bombeo) buscar_bombeo(s, ev);
        }
    }
    return r;
}

/* cambiar UNA entrada de la tabla de importaciones del exe (el juego llama a la nuestra) */
static void *parchear_iat(const char *dll, const char *funcion, void *nueva)
{
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir.VirtualAddress) return NULL;
    for (IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir.VirtualAddress); d->Name; d++) {
        if (lstrcmpiA((char *)(base + d->Name), dll)) continue;
        IMAGE_THUNK_DATA *nombres = (IMAGE_THUNK_DATA *)(base + (d->OriginalFirstThunk ? d->OriginalFirstThunk : d->FirstThunk));
        IMAGE_THUNK_DATA *real = (IMAGE_THUNK_DATA *)(base + d->FirstThunk);
        for (; nombres->u1.AddressOfData; nombres++, real++) {
            if (IMAGE_SNAP_BY_ORDINAL(nombres->u1.Ordinal)) continue;
            IMAGE_IMPORT_BY_NAME *n = (IMAGE_IMPORT_BY_NAME *)(base + nombres->u1.AddressOfData);
            if (lstrcmpA((char *)n->Name, funcion)) continue;
            DWORD prot;
            if (!VirtualProtect(&real->u1.Function, sizeof(void *), PAGE_READWRITE, &prot)) return NULL;
            void *viejo = (void *)real->u1.Function;
            real->u1.Function = (ULONG_PTR)nueva;
            VirtualProtect(&real->u1.Function, sizeof(void *), prot, &prot);
            return viejo;
        }
    }
    return NULL;
}

/* ── ★ EL SERVER, SIN PYTHON (12-nov) ──────────────────────────────────────
 * El cliente se conecta al Broker de 2009 (218.145.66.187:25000, de un XML de Data.dat), y el server
 * de juego que le da la lista apunta al MISMO lugar (herramientas/reglas_broker.py). Hasta acá eso lo
 * desviaba Frida (redirigir_cliente.py / eda_original.py). Ahora lo hace la DLL: el exe pide
 * `connect` por NOMBRE (EDA_limpio.exe, 2º descriptor de WS2_32), así que alcanza con su entrada de
 * la tabla de importaciones. Adónde: [red] server=host[:puerto] del ini (o EDA_SERVER, que manda);
 * vacío = no se desvía nada (el juego como antes). Sólo ESE destino: cualquier otro pasa igual. */
typedef int (WSAAPI *M_CONNECT)(SOCKET, const struct sockaddr *, int);
static M_CONNECT g_connect_real;
static char g_server[256];
static struct sockaddr_in g_destino;
static int g_destino_listo;
static long g_desviados;
static const BYTE BROKER_IP[4] = {218, 145, 66, 187};
#define BROKER_PUERTO 25000

static int resolver_server(void)
{
    if (g_destino_listo) return 1;
    char host[256];
    lstrcpynA(host, g_server, sizeof(host));
    int puerto = 25900;
    char *dp = strrchr(host, ':');
    if (dp) { *dp = 0; puerto = atoi(dp + 1); }
    unsigned long ip = inet_addr(host);
    if (ip == INADDR_NONE) {                         /* un nombre (un dominio): se resuelve acá */
        struct hostent *h = gethostbyname(host);
        if (h && h->h_addrtype == AF_INET && h->h_addr_list[0]) memcpy(&ip, h->h_addr_list[0], 4);
    }
    if (ip == INADDR_NONE || puerto <= 0 || puerto > 65535) {
        apuntar("  ⛔ server: no pude resolver «%s» (el juego va a 218.145.66.187, que no existe)", g_server);
        return 0;                                    /* sin guardar: el próximo connect reintenta */
    }
    memset(&g_destino, 0, sizeof(g_destino));
    g_destino.sin_family = AF_INET;
    g_destino.sin_port = htons((u_short)puerto);
    g_destino.sin_addr.s_addr = ip;
    g_destino_listo = 1;
    return 1;
}

/* ¿es el connect al Broker de 2009? (sólo IPv4, IP y puerto exactos) */
static int es_broker(const struct sockaddr *sa, int largo)
{
    const struct sockaddr_in *in = (const struct sockaddr_in *)sa;
    return sa && largo >= (int)sizeof(*in) && in->sin_family == AF_INET
        && ntohs(in->sin_port) == BROKER_PUERTO && !memcmp(&in->sin_addr, BROKER_IP, 4);
}

static int WSAAPI mi_connect(SOCKET s, const struct sockaddr *sa, int largo)
{
    if (es_broker(sa, largo) && resolver_server()) {
        struct sockaddr_in nuevo = *(const struct sockaddr_in *)sa;   /* ⚠ una copia: el del juego no se toca */
        nuevo.sin_port = g_destino.sin_port;
        nuevo.sin_addr = g_destino.sin_addr;
        g_desviados++;
        apuntar("  server: connect a 218.145.66.187:25000 → %s:%u (%ld)", inet_ntoa(nuevo.sin_addr),
                (unsigned)ntohs(nuevo.sin_port), g_desviados);
        return g_connect_real(s, (const struct sockaddr *)&nuevo, sizeof(nuevo));
    }
    return g_connect_real(s, sa, largo);
}

/* ── ★ EL LOGIN DEL LAUNCHER (12-nov) ──────────────────────────────────────
 * El juego lee su línea de comandos en `0x6229F0` (PROTOCOLO §5.1): `"exe" <BLOQUE>`, con BLOQUE =
 * hexadecimal de XOR("<A> <B>", la MAC en texto, en ciclo) → A a cuenta+0xF0 y B a +0x11A, y los dos
 * viajan al server en el 0x100F. Para que el launcher no tenga que saber de MAC ni de XOR, recibe
 * texto plano y la dll arma el bloque:
 *     "EDA_limpio.exe" <usuario> <ticket> [host:puerto]
 * (usuario = el uid de R2Beat; ticket = el que dio el server a cambio del pase del portero; el 3º, si
 * está, es el server: manda sobre el ini). Y si el juego se lanzó SIN comillas (que pisaba la MAC,
 * MEDICIONES §39), la dll le muestra la línea con comillas. En los demás casos, la línea no se toca. */
static char g_linea[1024];
static LPSTR WINAPI mi_get_command_line(void) { return g_linea; }

static int es_dato(const char *s, int n)
{
    if (n < 1 || n > 20) return 0;                   /* A y B: 21 caracteres UTF-16 con el 0 final */
    for (int i = 0; i < n; i++) {
        char c = s[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '-' || c == '_'))
            return 0;
    }
    return 1;
}

/* la MAC como la arma el juego: el 1er adaptador de GetAdaptersInfo, "%02X:%02X:…" */
static int mac_texto(char *out)
{
    ULONG largo = 0;
    if (GetAdaptersInfo(NULL, &largo) != ERROR_BUFFER_OVERFLOW || !largo) return 0;
    IP_ADAPTER_INFO *a = (IP_ADAPTER_INFO *)HeapAlloc(GetProcessHeap(), 0, largo);
    if (!a) return 0;
    int ok = GetAdaptersInfo(a, &largo) == ERROR_SUCCESS && a->AddressLength >= 6;
    if (ok) wsprintfA(out, "%02X:%02X:%02X:%02X:%02X:%02X", a->Address[0], a->Address[1], a->Address[2],
                      a->Address[3], a->Address[4], a->Address[5]);
    HeapFree(GetProcessHeap(), 0, a);
    return ok;
}

static void preparar_linea(void)
{
    const char *real = GetCommandLineA();
    const char *resto;
    char exe[MAX_PATH];
    int con_comillas = real[0] == '"';
    if (con_comillas) {
        const char *fin = strchr(real + 1, '"');
        resto = fin ? fin + 1 : real + lstrlenA(real);
    } else {
        resto = real;
        while (*resto && *resto != ' ' && *resto != '\t') resto++;
    }
    /* los argumentos, separados por espacios */
    const char *arg[4]; int largo[4], n = 0;
    for (const char *s = resto; *s && n < 4;) {
        while (*s == ' ' || *s == '\t') s++;
        if (!*s) break;
        arg[n] = s;
        while (*s && *s != ' ' && *s != '\t') s++;
        largo[n] = (int)(s - arg[n]);
        n++;
    }
    int login = n >= 2 && es_dato(arg[0], largo[0]) && es_dato(arg[1], largo[1]);
    if (!login && con_comillas) return;              /* nada que hacer: la línea queda como vino */
    if (!GetModuleFileNameA(NULL, exe, MAX_PATH)) return;
    wsprintfA(g_linea, "\"%s\"", exe);
    if (login) {
        char mac[24], plano[48];
        if (!mac_texto(mac)) {
            apuntar("  ⛔ login: no pude leer la MAC (GetAdaptersInfo): el juego entra sin usuario");
        } else {
            /* ⚠ wsprintfA no entiende «%.*s»: a mano (largo[0], largo[1] ≤ 20, ya verificados) */
            memcpy(plano, arg[0], largo[0]);
            plano[largo[0]] = ' ';
            memcpy(plano + largo[0] + 1, arg[1], largo[1]);
            plano[largo[0] + 1 + largo[1]] = 0;
            int lm = lstrlenA(mac), lp = lstrlenA(plano);
            char *p = g_linea + lstrlenA(g_linea);
            *p++ = ' ';
            for (int i = 0; i < lp; i++, p += 2)
                wsprintfA(p, "%02X", (BYTE)(plano[i] ^ mac[i % lm]));
            apuntar("  login: usuario %.*s y su ticket → el bloque del launcher (%d bytes)", largo[0], arg[0], lp);
        }
        if (n >= 3 && largo[2] < (int)sizeof(g_server) && !GetEnvironmentVariableA("EDA_SERVER", NULL, 0))
        {
            memcpy(g_server, arg[2], largo[2]);          /* el server del launcher (EDA_SERVER manda) */
            g_server[largo[2]] = 0;
        }
    } else {
        lstrcpynA(g_linea + lstrlenA(g_linea), resto, (int)sizeof(g_linea) - lstrlenA(g_linea));
        apuntar("  línea de comandos SIN comillas: el juego la ve con comillas (si no, pisaba la MAC)");
    }
    void *viejo = parchear_iat("KERNEL32.DLL", "GetCommandLineA", (void *)mi_get_command_line);
    if (!viejo) apuntar("  ⛔ no encontré GetCommandLineA en el exe: el login no llega");
}

/* ── ★ [p2p] QUE LOS JUEGOS SE ENCUENTREN (13-nov, MEDICIONES §52) ──────────────────────────────────────
 * Lo que el server necesita para darle a cada par la dirección DIRECTA del otro (servidor/relay.py ·
 * dir_udp) viaja en el 0x100F, y en las PCs de verdad llegaba roto:
 *  · mac=1 — LA MAC (la identidad P2P, cuenta+0x166). El juego copia el ticket del launcher a un búfer
 *    de 20 letras SIN lugar para el 0 (0x622E1D: 40 bytes en esp+0xB0) y después lo copia con wcscpy a
 *    cuenta+0x11A (0x622E49): con el ticket de 20 justos la copia sigue leyendo basura y PISA la MAC
 *    (medido en prod: «0x100F sin MAC válida» en las dos PCs, y en la de una se ve el «usuario ticket»
 *    en ASCII adentro). Con uno de 9 (MEDICIONES §45) no pasaba. Arreglo: la llamada a 0x6229F0 (la
 *    única, en 0x4E767B) pasa por acá; después, B termina en su letra 20 y la MAC vuelve a su lugar
 *    (UTF-16 en +0x166, y ASCII en +0x1C7 si también la pisó), con la misma MAC que lee el juego.
 *  · ip_privada=1 — LA IP PRIVADA (+0xDD del 0x100F). El juego la saca de gethostbyname(gethostname())
 *    y se queda con la PRIMERA (0x74FDAB): en una PC con VMware / VirtualBox / Hyper-V es la de la red
 *    virtual (medido: la de VMnet8, de VMware), a la que nadie de la casa llega. Arreglo: si el juego
 *    pregunta por el nombre de ESTA PC, la dll pone primero la IP por la que Windows sale hacia el
 *    server (un socket UDP «conectado» al server y getsockname: no manda nada). Sirve igual con cable o
 *    con WiFi: es la que se está usando. (Con una VPN que se lleva todo, sería la de la VPN.) */
static int g_p2p, g_p2p_mac, g_p2p_ip;
typedef void (__fastcall *M_CUENTA)(void *cuenta, void *nada);
#define CUENTA_LINEA 0x6229F0
#define LLAMADA_CUENTA 0x4E767B

static int es_mac16(const WCHAR *w)
{
    for (int i = 0; i < 17; i++) {
        WCHAR c = w[i];
        if (i % 3 == 2 ? c != ':' : !((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F'))) return 0;
    }
    return w[17] == 0;
}

static void __fastcall mi_cuenta_linea(void *cuenta, void *nada)
{
    (void)nada;
    ((M_CUENTA)(ULONG_PTR)CUENTA_LINEA)(cuenta, 0);
    BYTE *c = (BYTE *)cuenta;
    char mac[24];
    if (!legible(c + 0x11A, 0xC0) || !mac_texto(mac)) return;
    WCHAR *b = (WCHAR *)(c + 0x11A), *m16 = (WCHAR *)(c + 0x166);
    b[20] = 0;                                        /* B (el ticket): 21 UTF-16 con el 0 final */
    if (es_mac16(m16)) {
        apuntar("  [p2p] mac: la identidad del juego llegó sana");
        return;
    }
    for (int i = 0; i < 17; i++) m16[i] = (WCHAR)(BYTE)mac[i];
    m16[17] = 0;
    if (memcmp(c + 0x1C7, mac, 18)) memcpy(c + 0x1C7, mac, 18);
    apuntar("  [p2p] mac: ★ el ticket la había pisado; vuelve a su lugar (el server ya puede dar P2P directo)");
}

static void parche_mac(void)
{
    BYTE *p = (BYTE *)(ULONG_PTR)LLAMADA_CUENTA;
    LONG rel = (LONG)(CUENTA_LINEA - (LLAMADA_CUENTA + 5));
    DWORD prot;
    if (!legible(p, 5) || p[0] != 0xE8 || memcmp(p + 1, &rel, 4)) {
        apuntar("  [p2p] mac: ⚠ en 0x4E767B no está la llamada de EDA_limpio.exe: no se toca");
        return;
    }
    LONG nuevo = (LONG)((ULONG_PTR)mi_cuenta_linea - (LLAMADA_CUENTA + 5));
    if (!VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &prot)) return;
    memcpy(p + 1, &nuevo, 4);
    VirtualProtect(p, 5, prot, &prot);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    apuntar("  [p2p] mac: enganchada la lectura del login (0x4E767B)");
}

typedef struct hostent *(WSAAPI *M_GHBN)(const char *);
static M_GHBN g_ghbn_real;
static int resolver_server(void);

/* la IP local por la que Windows saldría hacia el server (o hacia internet, si no hay server) */
static unsigned long ip_de_salida(void)
{
    struct sockaddr_in a, yo;
    int largo = sizeof(yo);
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    if (g_server[0] && resolver_server()) a = g_destino;
    else { a.sin_addr.s_addr = inet_addr("8.8.8.8"); a.sin_port = htons(53); }
    SOCKET s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s == INVALID_SOCKET) return 0;
    unsigned long ip = 0;
    if (connect(s, (struct sockaddr *)&a, sizeof(a)) == 0 && getsockname(s, (struct sockaddr *)&yo, &largo) == 0)
        ip = yo.sin_addr.s_addr;
    closesocket(s);
    return ip;
}

static struct hostent *WSAAPI mi_gethostbyname(const char *nombre)
{
    char yo[256];
    int es_esta_pc = nombre && gethostname(yo, sizeof(yo)) == 0 && !lstrcmpiA(nombre, yo);
    /* ⚠ ANTES de pedir el nombre: resolver el server usa gethostbyname, que devuelve SIEMPRE el mismo
     *   búfer por hilo (pisaría la respuesta que le damos al juego) */
    unsigned long salida = es_esta_pc ? ip_de_salida() : 0;
    struct hostent *h = g_ghbn_real(nombre);
    if (!h || !salida || h->h_addrtype != AF_INET || !h->h_addr_list[0]) return h;
    for (int i = 0; h->h_addr_list[i]; i++) {
        if (memcmp(h->h_addr_list[i], &salida, 4)) continue;
        static int contado;
        if (i) {
            char *t = h->h_addr_list[0];
            h->h_addr_list[0] = h->h_addr_list[i];
            h->h_addr_list[i] = t;
        }
        if (!contado++) {
            struct in_addr en;
            memcpy(&en, &salida, 4);
            apuntar("  [p2p] ip_privada: %s (la de salida a la red%s)", inet_ntoa(en),
                    i ? "; ★ el juego iba a mandar otra: una red virtual" : ", y ya era la primera");
        }
        return h;
    }
    return h;
}

/* ── [hysteria] letras_32 (12-nov, de la PR #6 de Hysteria-xyz; en el bloque HYSTERIA, apagado) ─────────────────────
 * «Las letras salen cortadas a la mitad» en algunas PCs (lo vio el autor del PR; en la PC de prueba salen bien).
 * En 0x770a64 el juego arma la textura de cada letra empezando en 2×2 y duplicando hasta que entre
 * (`mov eax, 2`); el PR sostiene que con texturas chicas el driver da otro largo de fila del que el juego
 * usa. Con letras_32=1, la textura empieza en 32×32. Se toca SÓLO si los 5 bytes son los originales. */
static int g_letras32;
static int g_rui, g_hysteria, g_mazino;     /* los bloques de eda_d3d9.ini */
static void parche_letras(void)
{
    static const BYTE viejo[5] = {0xB8, 0x02, 0x00, 0x00, 0x00}, nuevo[5] = {0xB8, 0x20, 0x00, 0x00, 0x00};
    BYTE *p = (BYTE *)(ULONG_PTR)0x770A64;
    DWORD prot;
    if (!legible(p, 5) || memcmp(p, viejo, 5)) {
        apuntar("  [hysteria] letras_32: ⚠ en 0x770A64 no están los bytes de EDA_limpio.exe: no se toca");
        return;
    }
    if (!VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &prot)) return;
    memcpy(p, nuevo, 5);
    VirtualProtect(p, 5, prot, &prot);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    apuntar("  [hysteria] letras_32: las texturas de las letras empiezan en 32×32 (0x770A64)");
}

/* ── [hysteria] ping_verde (12-nov, de la PR #6 de Hysteria-xyz; el dueño del proyecto: «cambia el color por verde») ────────
 * En la sala, el número del ping de cada lugar se pinta SIEMPRE con el estilo 3 (rojo): el juego no mira el
 * valor (medido en el código: tu lugar, el que carga «-», un ping de verdad y el «-1000» sin dato pasan por
 * `push 3 · call 0x769770` en 0x537586 / 0x537630 / 0x5376D9). Con ping_verde=1 → 0.
 * ⛔ MEDIDO (12-nov, dos juegos en una sala, «3 de 3 sitios» puestos): el número SIGUE ROJO. 0x769770 no es
 *   el color: agrega ese valor a una lista de estados del rótulo (`+0x230`). El color viene de otro lado
 *   (🟡 la definición de la pantalla, en Data.dat). Queda apagado por defecto.
 * 🟡 PENDIENTE: el color según la calidad de la red (verde / amarillo / rojo, y uno neutro sin dato). */
static int g_ping_verde;
static void parche_ping_verde(void)
{
    static const DWORD sitios[3] = {0x537586, 0x537630, 0x5376D9};
    int puestos = 0;
    for (int i = 0; i < 3; i++) {
        BYTE *p = (BYTE *)(ULONG_PTR)sitios[i];
        DWORD prot;
        if (!legible(p, 2) || p[0] != 0x6A || p[1] != 0x03) continue;
        if (!VirtualProtect(p, 2, PAGE_EXECUTE_READWRITE, &prot)) continue;
        p[1] = 0x00;
        VirtualProtect(p, 2, prot, &prot);
        FlushInstructionCache(GetCurrentProcess(), p, 2);
        puestos++;
    }
    apuntar("  [hysteria] ping_verde: %d de 3 sitios con el ping en verde%s", puestos,
            puestos == 3 ? "" : " (⚠ los demás no tenían los bytes de EDA_limpio.exe: no se tocaron)");
}

/* ── ★ [mazino] LO QUE ANTES HACÍA FRIDA, AHORA EN LA DLL (14-nov) ──────────────────────────────────────────
 * Medido y probado en el juego con herramientas/eda_original.py (Frida) y pasado a C, para que llegue a los
 * jugadores con el launcher (sin Python). Las direcciones son las de EDA_limpio.exe (el del launcher): cada
 * sitio se VERIFICA antes de tocarlo y, si no coincide, no se toca y se anota.
 *  · botones=1 — los botones Clan / Messenger / Options de la barra de arriba no hacen nada en el cliente de
 *    2009. En el lobby se unen (0x4DF900, evento 3, controles 3·4·5) con el mismo delegado que el control 1
 *    (la llamada de 0x4F6061) pero con una función nuestra que manda un chat al server (/clan, /messenger,
 *    /opciones); en Shop / Inventory / Refinery / Skill (pantalla del costado 4–7) se leen del clic
 *    (y 8–58; x 465–539 / 547–621 / 629–703 en la pantalla de 800×600).
 *  · seleccion_multiple=1 — Ctrl+clic en la bolsa marca VARIAS casillas con la selección NATIVA del juego:
 *    cada casilla es un botón de un grupo de radio (grilla+0x3D8; +8 = la elegida = grilla+0x3E0) y se
 *    dibuja «elegida» (+0x128, el marco celeste) con su byte +0x248 = 1. «Sell» → Confirm (la llamada a
 *    0x54A990 de 0x51A12B, que manda el 0x1041 del ítem elegido) vende también las demás marcadas. Un clic
 *    sin Ctrl en otra casilla las suelta.
 *  · foco=1 — al cambiar de ventana EDA se PAUSABA (y parecía congelado): su WndProc (0x4026C0) para todo al
 *    desactivarse. Se le dice que sigue activo (salvo minimizado), y el mouse no se centra ni se encierra
 *    (SetPhysicalCursorPos / ClipCursor) mientras EDA no está al frente. */
static int g_mz_botones, g_mz_seleccion, g_mz_foco;
/* ★ opciones=1 (15-nov): el botón Options abre una ventana DE LA DLL, en la PC del jugador (antes mandaba
 *   «/opciones» y el server abría EDA-Opciones.py: sólo andaba con el server en la misma PC). Ver más abajo. */
static int g_mz_opciones, g_mz_atajos;
static void alternar_opciones(void);

/* las funciones del juego que se usan para armar y mandar un paquete (las mismas que usa él) */
typedef void *(__attribute__((thiscall)) *J_PINIT)(void *);
typedef void (__attribute__((thiscall)) *J_PCMD)(void *, DWORD);
typedef BYTE (__attribute__((thiscall)) *J_PBYTES)(void *, const void *, DWORD);
typedef void *(__cdecl *J_RED)(void);
typedef void (__attribute__((thiscall)) *J_MANDAR)(void *, void *);
typedef void (__attribute__((thiscall)) *J_PFIN)(void *);
typedef void *(__cdecl *J_CUENTA)(void);
typedef void *(__attribute__((thiscall)) *J_HIJO)(void *, DWORD);                /* ventana / control */
typedef void (__attribute__((thiscall)) *J_UNIR)(void *, int, int, void *);      /* 0x4DF900 */
typedef void (__attribute__((thiscall)) *J_VENDER)(void *, DWORD);               /* 0x54A990 */
#define JUEGO(t, a) ((t)(ULONG_PTR)(a))
static int g_mz_paquetes_ok;

static int firma(DWORD a, const char *hex)
{
    BYTE *p = (BYTE *)(ULONG_PTR)a;
    int n = lstrlenA(hex) / 3 + 1;
    if (!legible(p, n)) return 0;
    for (int i = 0; i < n; i++) {
        unsigned v = 0;
        for (int k = 0; k < 2; k++) {
            char c = hex[3 * i + k];
            v = v * 16 + (c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10);
        }
        if (p[i] != v) return 0;
    }
    return 1;
}

static void mandar_paquete(DWORD cmd, const void *cuerpo, DWORD largo)
{
    static BYTE p[0x1100];                      /* el paquete del juego (+0x1000 = su largo) */
    if (!g_mz_paquetes_ok) return;
    JUEGO(J_PINIT, 0x7425D0)(p);
    JUEGO(J_PCMD, 0x7426F0)(p, cmd);
    JUEGO(J_PBYTES, 0x7434F0)(p, cuerpo, largo);
    JUEGO(J_MANDAR, 0x744790)(JUEGO(J_RED, 0x7449F0)(), p);
    JUEGO(J_PFIN, 0x743390)(p);
}

/* un mensaje de chat al server (0x100D: u8 1 · u32 -1 · u32 0 · u32 largo · UTF-16) */
static void chat(const char *texto)
{
    BYTE c[13 + 2 * 64];
    int n = lstrlenA(texto);
    if (n > 64) n = 64;
    c[0] = 1;
    *(DWORD *)(c + 1) = 0xFFFFFFFF;
    *(DWORD *)(c + 5) = 0;
    *(DWORD *)(c + 9) = (DWORD)(2 * n);
    for (int i = 0; i < n; i++) *(WORD *)(c + 13 + 2 * i) = (BYTE)texto[i];
    mandar_paquete(0x100D, c, 13 + 2 * n);
    apuntar("  [mazino] botón → «%s»", texto);
}

/* ── botones del lobby ── */
static void __attribute__((thiscall)) boton_clan(void *pantalla, void *ev) { (void)pantalla; (void)ev; chat("/clan"); }
static void __attribute__((thiscall)) boton_msn(void *pantalla, void *ev) { (void)pantalla; (void)ev; chat("/messenger"); }
static void opciones_o_chat(void) { if (g_mz_opciones) alternar_opciones(); else chat("/opciones"); }
static void __attribute__((thiscall)) boton_opc(void *pantalla, void *ev) { (void)pantalla; (void)ev; opciones_o_chat(); }
static BYTE g_delegados[3][0x18];

static void __attribute__((thiscall)) mi_unir_lobby(void *lobby, int evento, int control, void *delegado)
{
    JUEGO(J_UNIR, 0x4DF900)(lobby, evento, control, delegado);
    if (!delegado || !legible(delegado, 0x18)) return;
    void *funciones[3] = {(void *)boton_clan, (void *)boton_msn, (void *)boton_opc};
    for (int i = 0; i < 3; i++) {
        memcpy(g_delegados[i], delegado, 0x18);
        *(void **)(g_delegados[i] + 8) = funciones[i];
        JUEGO(J_UNIR, 0x4DF900)(lobby, 3, 3 + i, g_delegados[i]);
    }
    apuntar("  [mazino] lobby: Clan, Messenger y Options unidos");
}

/* cambiar el destino de un `call rel32` del exe (sólo si apunta adonde se espera) */
static int desviar_llamada(DWORD sitio, DWORD esperado, void *nuevo, const char *que)
{
    BYTE *p = (BYTE *)(ULONG_PTR)sitio;
    LONG rel = (LONG)(esperado - (sitio + 5));
    DWORD prot;
    if (!legible(p, 5) || p[0] != 0xE8 || memcmp(p + 1, &rel, 4)) {
        apuntar("  [mazino] %s: ⚠ en 0x%lX no está la llamada de EDA_limpio.exe: no se toca", que, (unsigned long)sitio);
        return 0;
    }
    LONG n = (LONG)((ULONG_PTR)nuevo - (sitio + 5));
    if (!VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &prot)) return 0;
    memcpy(p + 1, &n, 4);
    VirtualProtect(p, 5, prot, &prot);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    return 1;
}

/* ── la selección múltiple ── */
typedef struct { DWORD serial; BYTE *celda; } MARCA;
static MARCA g_marcas[64];
static int g_nmarcas, g_pagina = -1;
static BYTE *g_cache_escena, *g_cache_ui, *g_cache_pest, *g_cache_g[5];
static DWORD g_pendiente, g_simple;
static BYTE *g_antes;

static BYTE *leer_ptr(const void *p) { return legible(p, 4) ? *(BYTE *const *)p : NULL; }

/* la pantalla del costado: 4 / 5 / 6 = Shop / Inventory / Refinery (con la bolsa), 7 = Skill */
static int pantalla_costado(BYTE *esc) { return esc && legible(esc + 0xDC, 4) ? *(int *)(esc + 0xDC) : -1; }

static BYTE *grilla(int *k_out)
{
    BYTE *esc = leer_ptr((void *)0x934554);
    int pc = pantalla_costado(esc);
    if (pc < 4 || pc > 6) { g_cache_escena = NULL; return NULL; }
    if (g_cache_escena != esc) {
        g_cache_escena = esc;
        g_cache_ui = leer_ptr(esc + 0x14);
        memset(g_cache_g, 0, sizeof(g_cache_g));
        BYTE *v = g_cache_ui ? JUEGO(J_HIJO, 0x7510F0)(g_cache_ui, 0x258) : NULL;
        g_cache_pest = v ? JUEGO(J_HIJO, 0x755200)(v, 0x2EE0) : NULL;
    }
    if (!g_cache_pest || !legible(g_cache_pest + 0x118, 4)) return NULL;
    int k = (int)*(DWORD *)(g_cache_pest + 0x118) - 0x2EE1;
    if (k < 0 || k > 4) return NULL;
    if (!g_cache_g[k]) {
        BYTE *v = JUEGO(J_HIJO, 0x7510F0)(g_cache_ui, 0x262 + 10 * k);
        g_cache_g[k] = v ? JUEGO(J_HIJO, 0x755200)(v, 0x2F44 + 100 * k) : NULL;
    }
    if (!g_cache_g[k] || !legible(g_cache_g[k] + 0x3D8, 0x10)) return NULL;
    *k_out = k;
    return g_cache_g[k];
}

static BYTE *elegida(void) { int k; BYTE *g = grilla(&k); return g ? leer_ptr(g + 0x3E0) : NULL; }

static BYTE *item_de(BYTE *celda) { return celda && legible(celda + 0x250, 4) ? leer_ptr(celda + 0x250) : NULL; }

static void pintar(BYTE *c, int si)
{
    if (!c || !legible(c, 0x250)) return;
    c[0x248] = si ? 1 : 0;
    *(BYTE **)(c + 0x244) = si ? c + 0x128 : c + (c[0x34] ? 0x1E0 : 0x184);
}

static void soltar(void)
{
    BYTE *sel = elegida();
    for (int i = 0; i < g_nmarcas; i++)
        if (g_marcas[i].celda != sel) pintar(g_marcas[i].celda, 0);
    g_nmarcas = 0;
}

static void repintar(void)
{
    BYTE *sel = elegida();
    for (int i = 0; i < g_nmarcas;) {
        BYTE *c = g_marcas[i].celda, *it = item_de(c);
        if (!it || !legible(it + 4, 4) || *(DWORD *)(it + 4) != g_marcas[i].serial) {
            /* la casilla ya no tiene ese ítem (se movió o se vendió): la marca se cae */
            if (c != sel) pintar(c, 0);
            g_marcas[i] = g_marcas[--g_nmarcas];
            continue;
        }
        if (c[0x248] != 1) pintar(c, 1);
        i++;
    }
}

static int marcada(DWORD serial)
{
    for (int i = 0; i < g_nmarcas; i++)
        if (g_marcas[i].serial == serial) return i;
    return -1;
}

static void marcar(DWORD serial, BYTE *celda)
{
    if (marcada(serial) < 0 && g_nmarcas < 64) {
        g_marcas[g_nmarcas].serial = serial;
        g_marcas[g_nmarcas].celda = celda;
        g_nmarcas++;
    }
}

static void revisar_inventario(void)
{
    int k = -1;
    BYTE *g = grilla(&k);
    if (!g || k != g_pagina) {
        if (g_nmarcas) { if (g) soltar(); g_nmarcas = 0; }
        g_pagina = g ? k : -1;
    }
    if (!g) return;
    DWORD ahora = GetTickCount();
    /* un clic SIN Ctrl que elige otra casilla = selección nueva: se sueltan las marcas (como en Windows).
     *   Un clic en «Sell» u otro botón no cambia la elegida: quedan. */
    if (g_simple && (LONG)(ahora - g_simple) >= 0) {
        g_simple = 0;
        BYTE *sel = leer_ptr(g + 0x3E0);
        if (g_nmarcas && g_antes && sel != g_antes) soltar();
    }
    if (!g_pendiente || (LONG)(ahora - g_pendiente) < 0) { repintar(); return; }
    g_pendiente = 0;
    BYTE *celda = leer_ptr(g + 0x3E0), *it = item_de(celda);
    if (!it || !legible(it + 4, 4)) { repintar(); return; }
    DWORD serial = *(DWORD *)(it + 4);
    /* la primera marca con Ctrl incluye la casilla que ya estaba elegida (como en Windows) */
    if (!g_nmarcas && g_antes && g_antes != celda) {
        BYTE *it2 = item_de(g_antes);
        if (it2 && legible(it2 + 4, 4)) marcar(*(DWORD *)(it2 + 4), g_antes);
    }
    int i = marcada(serial);
    if (i >= 0) { g_marcas[i] = g_marcas[--g_nmarcas]; pintar(celda, 0); }
    else marcar(serial, celda);
    repintar();
    apuntar("  [mazino] marcas: %d", g_nmarcas);
}

/* ★ (15-nov) EL PRECIO DEL DIÁLOGO «Sell»: 0x526820 (el clic en Sell) busca el precio de la elegida en la tabla
 *   de la escena (+0x160, 0x5D6ED0 por el número del ítem, item+8 → +4 = oro) y arma el texto con 0x4DDBD0
 *   (Format(salida, plantilla, nombre, oro), la llamada de 0x5269C6). Con varias marcadas, se le pasa la SUMA del
 *   precio de cada una (la misma búsqueda del juego). El server cobra cada una por su cuenta (servidor/tienda.py:
 *   su propio precio, y un serial ya vendido no se paga dos veces). */
typedef void *(__attribute__((thiscall)) *J_PRECIO)(void *, DWORD);         /* 0x5D6ED0 */
typedef void (__cdecl *J_FORMATO)(void *, void *, void *, DWORD);           /* 0x4DDBD0 (varargs) */
static int g_mz_precio_ok;
static DWORD precio_de(BYTE *tabla, BYTE *it)
{
    if (!tabla || !it || !legible(it + 8, 2)) return 0;
    BYTE *e = JUEGO(J_PRECIO, 0x5D6ED0)(tabla, *(WORD *)(it + 8));
    return e && legible(e + 4, 4) ? *(DWORD *)(e + 4) : 0;
}
static void __cdecl mi_formato_venta(void *salida, void *plantilla, void *nombre, DWORD precio)
{
    DWORD total = precio;
    BYTE *esc = leer_ptr((void *)0x934554), *tabla = esc ? esc + 0x160 : NULL, *sel = elegida();
    if (g_mz_precio_ok && g_mz_seleccion && g_nmarcas > 1 && tabla) {
        DWORD suma = 0;
        int n = 0, con_elegida = 0, ok = 1;
        for (int i = 0; i < g_nmarcas && ok; i++) {
            BYTE *it = item_de(g_marcas[i].celda);
            if (!it || !legible(it + 4, 4) || *(DWORD *)(it + 4) != g_marcas[i].serial) continue;
            DWORD p = precio_de(tabla, it);
            if (!p) ok = 0;
            suma += p;
            n++;
            if (g_marcas[i].celda == sel) con_elegida = 1;
        }
        if (ok && !con_elegida) { suma += precio; n++; }            /* (la elegida no estaba marcada) */
        if (ok && n > 1) {
            total = suma;
            apuntar("  [mazino] venta: %d ítems · total %lu (uno: %lu)", n, (unsigned long)total, (unsigned long)precio);
        }
    }
    JUEGO(J_FORMATO, 0x4DDBD0)(salida, plantilla, nombre, total);
}

/* «Sell» → Confirm: el juego manda el 0x1041 de la elegida; nosotros, el de cada una de las demás */
static void __attribute__((thiscall)) mi_vender(void *escena, DWORD serial)
{
    JUEGO(J_VENDER, 0x54A990)(escena, serial);
    if (!g_mz_seleccion || !g_nmarcas) return;
    BYTE *cuenta = JUEGO(J_CUENTA, 0x623E60)();
    int otros = 0;
    if (cuenta && legible(cuenta + 0x2B8, 4)) {
        for (int i = 0; i < g_nmarcas; i++) {
            if (g_marcas[i].serial == serial) continue;
            DWORD cuerpo[2] = {*(DWORD *)(cuenta + 0x2B8), g_marcas[i].serial};
            mandar_paquete(0x1041, cuerpo, 8);
            otros++;
        }
    }
    soltar();
    if (otros) apuntar("  [mazino] venta múltiple: %d ítems", otros + 1);
}

/* los botones Clan / Options / Messenger en las pantallas del costado (el juego no los une a nada) */
static void barra(HWND h, LPARAM l)
{
    BYTE *esc = leer_ptr((void *)0x934554);
    int pc = pantalla_costado(esc);
    RECT r;
    int x = (short)LOWORD(l), y = (short)HIWORD(l);
    if (GetClientRect(h, &r) && r.right > 0 && r.bottom > 0) {        /* (en la pantalla de 800×600) */
        x = x * 800 / r.right;
        y = y * 600 / r.bottom;
    }
    if (pc < 4 || pc > 7) {
        /* (15-nov, MEDIR) un clic donde están Clan / Options / Messenger en OTRA pantalla (la sala de una stage
         *   creada): se anota la escena para reconocerla; todavía no se actúa (en la partida esa zona es juego) */
        if (y >= 8 && y <= 58 && x >= 465 && x <= 703)
            apuntar("  [mazino] (medir) clic en la barra: x %d · pantalla %d · escena 0x%08lX vtable 0x%08lX", x, pc,
                    (unsigned long)(ULONG_PTR)esc, (unsigned long)(ULONG_PTR)(esc ? leer_ptr(esc) : NULL));
        return;
    }
    if (y < 8 || y > 58) return;
    if (x >= 465 && x <= 539) chat("/clan");
    else if (x >= 547 && x <= 621) opciones_o_chat();
    else if (x >= 629 && x <= 703) chat("/messenger");
}

/* ── el foco ── */
static HWND g_ventana_juego;
static WNDPROC g_wndproc_viejo;

static LRESULT CALLBACK mi_wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (!IsIconic(h)) {
        if (m == WM_ACTIVATE && LOWORD(w) == WA_INACTIVE) w |= 1;   /* «sigue activo» (salvo minimizado) */
        else if ((m == WM_ACTIVATEAPP || m == WM_NCACTIVATE) && w == 0) w = 1;
    }
    return CallWindowProcA(g_wndproc_viejo, h, m, w, l);
}

static void vigilar_wndproc(HWND h)
{
    WNDPROC actual = (WNDPROC)(LONG_PTR)GetWindowLongA(h, GWL_WNDPROC);
    if (!actual || actual == mi_wndproc) return;
    g_wndproc_viejo = actual;
    SetWindowLongA(h, GWL_WNDPROC, (LONG)(ULONG_PTR)mi_wndproc);
    apuntar("  [mazino] foco: WndProc 0x%08lX → EDA no se pausa al cambiar de ventana", (unsigned long)(ULONG_PTR)actual);
}

/* ★ (15-nov) con una ventana nuestra abierta (Options) el juego NO tiene el mouse: en pantalla completa sin bordes
 *   el juego tapa todo y, al seguir «al frente», centraba y encerraba el cursor: los clics pasaban por debajo */
static volatile LONG g_panel_abierto;
static int juego_al_frente(void)
{
    return !g_panel_abierto && (!g_ventana_juego || GetForegroundWindow() == g_ventana_juego);
}

typedef BOOL (WINAPI *M_SETCUR)(int, int);
typedef BOOL (WINAPI *M_CLIP)(const RECT *);
static M_SETCUR g_setcur_real;
static M_CLIP g_clip_real;
static BOOL WINAPI mi_setcur(int x, int y) { return juego_al_frente() ? g_setcur_real(x, y) : TRUE; }
static BOOL WINAPI mi_clip(const RECT *r) { return g_clip_real(juego_al_frente() ? r : NULL); }


/* ── ★ LAS OPTIONS, EN LA DLL: el panel de paneles/EDA-Opciones.py, con su mismo diseño (eda_opciones.c) ── */
#include "eda_opciones.c"

/* ── el bombeo de mensajes del juego (PeekMessageA, su hilo principal) ── */
typedef BOOL (WINAPI *M_PEEK)(LPMSG, HWND, UINT, UINT, UINT);
static M_PEEK g_peek_real;
static DWORD g_hilo_juego;
static long g_vueltas;

static BOOL WINAPI mi_peek(LPMSG m, HWND h, UINT a, UINT b, UINT r)
{
    BOOL hay = g_peek_real(m, h, a, b, r);
    DWORD yo = GetCurrentThreadId();
    if (!g_hilo_juego) g_hilo_juego = yo;
    if (yo != g_hilo_juego) return hay;
    if (hay && m && m->hwnd) {
        if (!g_ventana_juego) g_ventana_juego = GetAncestor(m->hwnd, GA_ROOT);
        if (g_mz_seleccion && m->message == WM_LBUTTONDOWN) g_antes = elegida();   /* la elegida ANTES del clic */
        /* ★ F10 Options · F11 Messenger · F12 Clan (antes EDA-Atajos.py, sólo en la PC con Python); F10 llega
         *   como tecla de sistema. Sin repetición (bit 30 = ya estaba apretada). */
        if (g_mz_atajos && (m->message == WM_KEYDOWN || m->message == WM_SYSKEYDOWN) && !(m->lParam & (1L << 30))) {
            if (m->wParam == VK_F8 && GetKeyState(VK_CONTROL) < 0) anillo_en_vivo(!g_buferes);
            else if (m->wParam == VK_F10) { apuntar("  [mazino] F10"); opciones_o_chat(); }
            else if (m->wParam == VK_F11) chat("/messenger");
            else if (m->wParam == VK_F12) chat("/clan");
        }
        if (m->message == WM_LBUTTONUP) {
            if (g_mz_seleccion && (m->wParam & MK_CONTROL)) g_pendiente = GetTickCount() + 120;
            else {
                if (g_mz_seleccion) g_simple = GetTickCount() + 120;
                if (g_mz_botones) barra(m->hwnd, m->lParam);
            }
        }
    }
    ++g_vueltas;
    if (g_mz_foco && g_ventana_juego && (g_vueltas & 255) == 1) vigilar_wndproc(g_ventana_juego);
    if (g_mz_seleccion && (g_pendiente || g_simple || (g_vueltas & 3) == 0)) revisar_inventario();
    if (g_opc_n) opc_correr_cola();
    if (g_ubicar && (g_vueltas & 127) == 0) opc_ubicar_tick();
    if ((g_pantalla_pedida >= 0 || g_sin_bordes) && (g_vueltas & 63) == 0) opc_pantalla_tick();
    return hay;
}

static void poner_mazino(void)
{
    /* las funciones del juego para mandar un paquete: verificadas antes de usarlas */
    g_mz_paquetes_ok = firma(0x7425D0, "8b c1 33 c9") && firma(0x7426F0, "66 8b 54 24") && firma(0x7434F0, "53 55 8b 6c")
        && firma(0x7449F0, "64 a1 00 00") && firma(0x744790, "6a ff 68 46") && firma(0x743390, "57 8b b9 00")
        && firma(0x623E60, "64 a1 00 00") && firma(0x7510F0, "8b 01 85 c0") && firma(0x755200, "53 8b 99 dc")
        && firma(0x4DF900, "6a ff 68 80") && firma(0x54A990, "6a ff 64 a1");
    if (!g_mz_paquetes_ok) {
        apuntar("  [mazino] ⚠ las funciones del juego no están donde en EDA_limpio.exe: botones y selección apagados");
        g_mz_botones = g_mz_seleccion = 0;
    }
    if (g_mz_botones && desviar_llamada(0x4F6061, 0x4DF900, (void *)mi_unir_lobby, "botones"))
        apuntar("  [mazino] botones: enganchado el lobby (0x4F6061) y las pantallas del costado");
    if (g_mz_seleccion && desviar_llamada(0x51A12B, 0x54A990, (void *)mi_vender, "seleccion_multiple"))
        apuntar("  [mazino] seleccion_multiple: Ctrl+clic en la bolsa; «Sell» vende todas (0x51A12B)");
    if (g_mz_seleccion && firma(0x5D6ED0, "51 56 8b f1 8d 44 24 0c") && firma(0x4DDBD0, "8b 4c 24 08 8d 44 24 0c")
        && desviar_llamada(0x5269C6, 0x4DDBD0, (void *)mi_formato_venta, "precio_total")) {
        g_mz_precio_ok = 1;
        apuntar("  [mazino] seleccion_multiple: el diálogo de venta muestra la suma de las marcadas (0x5269C6)");
    }
    if (g_mz_foco) {
        g_setcur_real = (M_SETCUR)parchear_iat("user32.dll", "SetPhysicalCursorPos", (void *)mi_setcur);
        g_clip_real = (M_CLIP)parchear_iat("user32.dll", "ClipCursor", (void *)mi_clip);
        if (!g_setcur_real || !g_clip_real) apuntar("  [mazino] foco: ⚠ no encontré SetPhysicalCursorPos / ClipCursor en el exe");
    }
    if (g_mz_opciones && !g_opc_cs_lista) { InitializeCriticalSection(&g_opc_cs); g_opc_cs_lista = 1; }
    if (g_mz_opciones && !consola_del_juego())
        apuntar("  [mazino] opciones: (la consola del juego todavía no existe: se busca al usarla)");
    if (g_mz_botones || g_mz_seleccion || g_mz_foco || g_mz_opciones || g_mz_atajos) {
        g_peek_real = (M_PEEK)parchear_iat("user32.dll", "PeekMessageA", (void *)mi_peek);
        if (!g_peek_real) {
            apuntar("  [mazino] ⚠ no encontré PeekMessageA en el exe: sin selección múltiple, sin foco, sin botones del costado");
            g_mz_seleccion = 0;
        }
    }
}

/* ★ las TRAMPAS del desempacado (sin Frida): una llamada que no se pudo resolver salta a
 *   0xD0000000 + sitio − 0x400000 y el juego se cae. Queda anotado QUÉ sitio en eda_d3d9.log, para
 *   que un jugador lo pueda mandar (documentacion/APIS_A_MANO.md). No cambia nada: sigue la caída. */
/* ── ★ LA CAJA NEGRA (12-nov, como la de R2Beat: fuente/cajanegra.c de ese proyecto) ─────────────────
 * Unos amigos dijeron que el juego se les caía CON la dll y SIN ella no. Para que una caída diga DÓNDE:
 * cada excepción grave (acceso inválido, instrucción ilegal, pila llena, división por 0, montón roto,
 * pila corrompida) queda en eda_d3d9.log con el MÓDULO donde pasó («exe 0x…» = el juego; «eda_d3d9.dll» =
 * NUESTRA dll; otro = el driver o Windows), los registros y las direcciones de código de la pila (la cadena
 * de llamadas aproximada). Tope 3 por arranque; dice «primera oportunidad» porque puede ser una que el
 * juego mismo maneja. Sólo MIRA: el juego sigue igual. [cajanegra] activo=0 la apaga. Además el juego
 * escribe su propio informe al caerse (EDA_limpio.rpt / .dmp, al lado del exe). */
static int g_caja = 1;
static long g_caja_n;

static void donde_es(DWORD a, char *out)
{
    HMODULE m = NULL;
    char ruta[MAX_PATH];
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)(ULONG_PTR)a, &m) && m && GetModuleFileNameA(m, ruta, MAX_PATH)) {
        char *b = strrchr(ruta, '\\');
        HMODULE yo = NULL;
        GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)donde_es, &yo);
        /* ⚠ la nuestra y la de Windows se llaman IGUAL (d3d9.dll): se dicen distinto */
        const char *nombre = m == yo ? "NUESTRA-d3d9" : (m == g_real ? "d3d9-de-Windows" : (b ? b + 1 : ruta));
        if (m == GetModuleHandleA(NULL)) wsprintfA(out, "exe 0x%08lX", (unsigned long)a);
        else wsprintfA(out, "%s+0x%lX", nombre, (unsigned long)(a - (DWORD)(ULONG_PTR)m));
    } else {
        wsprintfA(out, "0x%08lX", (unsigned long)a);
    }
}

static LONG WINAPI mi_excepcion(EXCEPTION_POINTERS *e)
{
    DWORD eip = (DWORD)(ULONG_PTR)e->ExceptionRecord->ExceptionAddress;
    if (eip >= 0xD0000000u && eip < 0xD0600000u) {
        apuntar("⛔ el juego llegó a una llamada de Windows SIN RESOLVER: sitio 0x%lX (abrí un issue con "
                "este número)", (unsigned long)(eip - 0xD0000000u + 0x400000u));
        return EXCEPTION_CONTINUE_SEARCH;
    }
    DWORD cod = e->ExceptionRecord->ExceptionCode;
    if (!g_caja || (cod != 0xC0000005 && cod != 0xC000001D && cod != 0xC00000FD && cod != 0xC0000094
                    && cod != 0xC0000096 && cod != 0xC0000374 && cod != 0xC0000409))
        return EXCEPTION_CONTINUE_SEARCH;
    if (InterlockedIncrement(&g_caja_n) > 3) return EXCEPTION_CONTINUE_SEARCH;
    char donde[MAX_PATH + 32], dir_txt[MAX_PATH + 32];
    donde_es(eip, donde);
    const char *que = "";
    dir_txt[0] = 0;
    if (cod == 0xC0000005 && e->ExceptionRecord->NumberParameters >= 2) {
        ULONG_PTR tipo = e->ExceptionRecord->ExceptionInformation[0];
        que = tipo == 1 ? " · escribe en" : (tipo == 8 ? " · ejecuta" : " · lee");
        wsprintfA(dir_txt, " 0x%08lX", (unsigned long)e->ExceptionRecord->ExceptionInformation[1]);
    }
    HMODULE yo = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)mi_excepcion, &yo);
    HMODULE ahi = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)(ULONG_PTR)eip, &ahi);
    CONTEXT *r = e->ContextRecord;
    apuntar("⛔⛔ [cajanegra] EXCEPCION 0x%08lX en %s%s%s · primera oportunidad%s", (unsigned long)cod, donde, que,
            dir_txt, (ahi && ahi == yo) ? " · ★ ES EN NUESTRA DLL" : "");
    apuntar("   [cajanegra] eax=%08lX ebx=%08lX ecx=%08lX edx=%08lX esi=%08lX edi=%08lX ebp=%08lX esp=%08lX",
            r->Eax, r->Ebx, r->Ecx, r->Edx, r->Esi, r->Edi, r->Ebp, r->Esp);
    /* la pila: las direcciones que caen en código de algún módulo (de la más cercana a la más lejana) */
    char linea[1200];
    int n = 0, k = 0;
    linea[0] = 0;
    DWORD *p = (DWORD *)(ULONG_PTR)r->Esp;
    DWORD *tope = (DWORD *)((NT_TIB *)NtCurrentTeb())->StackBase;
    for (int i = 0; i < 256 && p + i < tope && k < 12 && n < (int)sizeof(linea) - 80; i++) {
        HMODULE m = NULL;
        DWORD v = p[i];
        if (v < 0x10000 || !GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
                                               | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                               (LPCSTR)(ULONG_PTR)v, &m) || !m)
            continue;
        char d[MAX_PATH + 32];
        donde_es(v, d);
        n += wsprintfA(linea + n, "%s%s", k ? " · " : "", d);
        k++;
    }
    apuntar("   [cajanegra] la pila (de la más cercana a la más lejana): %s", linea);
    return EXCEPTION_CONTINUE_SEARCH;
}

/* ★ esperar hasta el próximo cuadro. Sin eventos de red: Sleep mientras falte más de ~2 ms (con
 *   timeBeginPeriod(1), Sleep(1) ≈ 1 ms) y girar el último tramo. CON eventos: esperarlos con el tiempo
 *   que falta como plazo; si llega un mensaje, soltar YA (sin correr la grilla de los cuadros). */
static LARGE_INTEGER g_ultimo;
static void esperar_tope(void)
{
    if (g_tope <= 0) return;
    LARGE_INTEGER ahora;
    QueryPerformanceCounter(&ahora);
    LONGLONG paso = g_frec.QuadPart / g_tope;
    if (g_proximo.QuadPart == 0 || ahora.QuadPart - g_proximo.QuadPart > paso) {
        g_proximo.QuadPart = ahora.QuadPart + paso;      /* atrasados (o el 1er cuadro): no recuperar */
        g_ultimo = ahora;
        return;
    }
    for (;;) {
        QueryPerformanceCounter(&ahora);
        double falta = ms_entre(ahora, g_proximo);
        if (falta <= 0) break;
        /* ★★ con el bombeo: esperar el evento de red con el tiempo que falta; si llega algo, el JUEGO lo
         *   atiende (0x74D530) y seguimos esperando el turno: los cuadros quedan fijos en el tope */
        if (g_red && g_bombeo && g_usar_bombeo && falta > 0.3) {
            DWORD plazo = falta > 1.5 ? (DWORD)(falta - 1.0) : 0;
            if (WaitForSingleObject(g_ev_bombeo, plazo) == WAIT_OBJECT_0) {
                g_bombeo(g_socket_obj);
                g_bombeos++;
            } else if (plazo == 0) {
                YieldProcessor();
            }
            continue;
        }
        if (g_red && g_neventos && falta > 0.5) {
            /* ⚠ un piso de 1 ms entre cuadros: si un evento quedara levantado (el juego no lo leyó),
             *   no se dispara a miles de cuadros por segundo */
            if (ms_entre(g_ultimo, ahora) >= 1.0
                    && WaitForMultipleObjects(g_neventos, g_eventos, FALSE, falta > 2.0 ? (DWORD)(falta - 1.0) : 0)
                       < WAIT_OBJECT_0 + (DWORD)g_neventos) {
                g_despertadas++;
                QueryPerformanceCounter(&g_ultimo);
                /* ★ con tope ESTRICTO el cuadro adelantado «gasta» el turno: el próximo va un paso
                 *   más allá, así el promedio queda EXACTO en el tope (nunca hay cuadros de más) */
                if (g_estricto) g_proximo.QuadPart += paso;
                return;                                   /* ★ llegó algo: el juego lo lee ya */
            }
            if (falta > 2.0 && ms_entre(g_ultimo, ahora) < 1.0) Sleep(1);
            else if (falta <= 2.0) YieldProcessor();
            continue;
        }
        if (falta > 2.0) Sleep(1);
        else YieldProcessor();
    }
    g_proximo.QuadPart += paso;
    QueryPerformanceCounter(&g_ultimo);
}

/* ── el contador: «FPS 120» con segmentos ─────────────────────────────── */
typedef struct { float x, y, z, rhw; DWORD color; } VERTICE;
static VERTICE g_v[600];
static int g_nv;

static void rect(float x, float y, float w, float h, DWORD c)
{
    if (g_nv + 6 > (int)(sizeof(g_v) / sizeof(g_v[0]))) return;
    VERTICE q[4] = {{x, y, 0, 1, c}, {x + w, y, 0, 1, c}, {x, y + h, 0, 1, c}, {x + w, y + h, 0, 1, c}};
    int orden[6] = {0, 1, 2, 2, 1, 3};
    for (int i = 0; i < 6; i++) g_v[g_nv++] = q[orden[i]];
}

/* segmentos a..g: bit 0 = a (arriba) … bit 6 = g (medio) */
static const unsigned char SEG_DIGITO[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};
enum { SEG_F = 0x71, SEG_P = 0x73, SEG_S = 0x6D };

static void segmentos(float x, float y, unsigned char m, DWORD c)
{
    const float w = 9, h = 16, t = 2;
    if (m & 0x01) rect(x, y, w, t, c);                        /* a */
    if (m & 0x02) rect(x + w - t, y, t, h / 2, c);            /* b */
    if (m & 0x04) rect(x + w - t, y + h / 2, t, h / 2, c);    /* c */
    if (m & 0x08) rect(x, y + h - t, w, t, c);                /* d */
    if (m & 0x10) rect(x, y + h / 2, t, h / 2, c);            /* e */
    if (m & 0x20) rect(x, y, t, h / 2, c);                    /* f */
    if (m & 0x40) rect(x, y + h / 2 - t / 2, w, t, c);        /* g */
}

static void dibujar_contador(void *dev)
{
    void **vt = VT(dev);
    char num[12];
    int n = sprintf(num, "%d", g_fps);
    g_nv = 0;
    float x0 = 6, y0 = 6, paso = 13;
    rect(x0 - 4, y0 - 4, paso * (4 + n) + 6, 24, 0xFF000000);  /* el fondo negro */
    DWORD verde = g_tope > 0 && g_fps > g_tope + 5 ? 0xFFFF6040 : 0xFF40FF60;
    segmentos(x0, y0, SEG_F, verde);
    segmentos(x0 + paso, y0, SEG_P, verde);
    segmentos(x0 + 2 * paso, y0, SEG_S, verde);
    for (int i = 0; i < n; i++) segmentos(x0 + (4 + i) * paso, y0, SEG_DIGITO[num[i] - '0'], 0xFFFFFFFF);

    /* ⚠ el state block es DEL DISPOSITIVO que lo creó: el juego crea OTRO al entrar a la partida, y
     *   aplicarle el del viejo le ponía estados ajenos (glitches) y el contador desaparecía (11-nov).
     *   El del dispositivo viejo se abandona sin tocarlo (ese dispositivo ya puede no existir). */
    if (g_bloque && g_bloque_dev != dev) g_bloque = NULL;
    if (!g_bloque && ((M_CSB)vt[I_CREATESB])(dev, 1 /* D3DSBT_ALL */, &g_bloque) != 0) g_bloque = NULL;
    g_bloque_dev = dev;
    if (g_bloque) ((M_SB)VT(g_bloque)[4])(g_bloque);            /* Capture */
    ((M_SIN)vt[I_BEGINSCENE])(dev);
    ((M_UNO)vt[I_SETVS])(dev, NULL);
    ((M_UNO)vt[I_SETPS])(dev, NULL);
    ((M_PTR)vt[I_SETTEXTURE])(dev, 0, NULL);
    ((M_RS)vt[I_SETFVF])(dev, 0x044, 0);                         /* XYZRHW | DIFFUSE */
    static const DWORD estados[][2] = {{7, 0} /* ZENABLE */, {14, 0} /* ZWRITE */, {15, 0} /* ALPHATEST */,
        {27, 0} /* ALPHABLEND */, {22, 1} /* CULL NONE */, {137, 0} /* LIGHTING */, {28, 0} /* FOG */,
        {52, 0} /* STENCIL */, {174, 0} /* SCISSOR */, {168, 0xF} /* COLORWRITE */, {8, 3} /* SOLID */};
    for (unsigned i = 0; i < sizeof(estados) / sizeof(estados[0]); i++)
        ((M_RS)vt[I_SETRS])(dev, estados[i][0], estados[i][1]);
    ((M_TSS)vt[I_SETTSS])(dev, 0, 1, 2);        /* COLOROP = SELECTARG1 */
    ((M_TSS)vt[I_SETTSS])(dev, 0, 2, 0);        /* COLORARG1 = DIFFUSE */
    ((M_TSS)vt[I_SETTSS])(dev, 0, 4, 2);        /* ALPHAOP = SELECTARG1 */
    ((M_TSS)vt[I_SETTSS])(dev, 0, 5, 0);        /* ALPHAARG1 = DIFFUSE */
    ((M_TSS)vt[I_SETTSS])(dev, 1, 1, 1);        /* etapa 1: DISABLE */
    ((M_DPUP)vt[I_DPUP])(dev, 4 /* TRIANGLELIST */, g_nv / 3, g_v, sizeof(VERTICE));
    ((M_SIN)vt[I_ENDSCENE])(dev);
    if (g_bloque) ((M_SB)VT(g_bloque)[5])(g_bloque);            /* Apply: todo como estaba */
}

/* ── los ganchos ───────────────────────────────────────────────────────── */
static long WINAPI mi_present(void *dev, const RECT *a, const RECT *b, HWND w, const void *r)
{
    LARGE_INTEGER ahora;
    QueryPerformanceCounter(&ahora);
    g_cuadros++;
    if (g_avisado_sin_present) { apuntar("  (medir) vuelve el Present (dispositivo 0x%08lX)", (unsigned long)(ULONG_PTR)dev); g_avisado_sin_present = 0; }
    g_ultimo_present = GetTickCount();
    g_dibujos_sin_present = 0;
    /* (sólo para PROBAR la caja negra: EDA_PROBAR_CAJA=1 hace caer a NUESTRA dll en el cuadro 60) */
    static int probar = -1, cuadro;
    if (probar < 0) {
        char v[8];
        probar = GetEnvironmentVariableA("EDA_PROBAR_CAJA", v, sizeof(v)) && v[0] == '1';
    }
    if (probar && ++cuadro == 60) *(volatile int *)(ULONG_PTR)0x10 = 1;
    if (g_ventana.QuadPart == 0) g_ventana = ahora;
    double ms = ms_entre(g_ventana, ahora);
    if (ms >= 500) {
        static int ventanas;
        g_fps = (int)(g_cuadros * 1000.0 / ms + 0.5);
        g_cuadros = 0;
        g_ventana = ahora;
        if (++ventanas % 60 == 0)                                   /* cada ~30 s */
        {
            apuntar("  %d cuadros/s · despertadas %ld · bloqueos a la copia %ld · subidas al anillo %ld (%ld B en promedio)"
                    " · fuente corregida %ld", g_fps, g_despertadas, g_convertidos, g_subidos,
                    g_subidos ? g_subidos_bytes / g_subidos : 0, g_desfasadas);
            if (g_medir_escritura)
                apuntar("  escritura: %ld de %ld bloqueos CAMBIAN algo · promedio %ld B · máx %ld · empiezan en 0: %ld · siguen al anterior: %ld",
                        g_med_n, g_convertidos, g_med_n ? g_med_bytes / g_med_n : 0, g_med_max, g_med_desde0, g_med_siguiente);
        }
    }
    if (g_mostrar) dibujar_contador(dev);
    long hr = g_present_real(dev, a, b, w, r);
    esperar_tope();
    return hr;
}

static long WINAPI mi_reset(void *dev, void *pp)
{
    if (g_bloque) {
        if (g_bloque_dev == dev)
            ((M_SB)VT(g_bloque)[2])(g_bloque);                     /* Release (si no, Reset falla) */
        g_bloque = NULL;                                          /* (el de otro dispositivo: ni tocarlo) */
    }
    ajustar_pp(pp);
    long hr = g_reset_real(dev, pp);
    apuntar("Reset -> 0x%08lx", (unsigned long)hr);
    return hr;
}

static void poner(void **vt, int i, void *nuevo, void **viejo)
{
    if (vt[i] == nuevo) return;
    DWORD prot;
    if (!VirtualProtect(&vt[i], sizeof(void *), PAGE_EXECUTE_READWRITE, &prot)) return;
    *viejo = vt[i];
    vt[i] = nuevo;
    VirtualProtect(&vt[i], sizeof(void *), prot, &prot);
}

static long WINAPI mi_crear_dispositivo(void *d3d, UINT adaptador, DWORD tipo, HWND foco, DWORD flags,
                                        void *pp, void **dev)
{
    ajustar_pp(pp);
    long hr = g_creardev_real(d3d, adaptador, tipo, foco, flags, pp, dev);
    apuntar("CreateDevice(adaptador %u, flags 0x%lx, swap %lu, pflags 0x%lx, intervalo 0x%lx) -> 0x%08lx",
            adaptador, (unsigned long)flags, (unsigned long)((DWORD *)pp)[6], (unsigned long)((DWORD *)pp)[11],
            (unsigned long)((DWORD *)pp)[13], (unsigned long)hr);
    if (hr == 0 && dev && *dev) {
        void **vt = VT(*dev);
        poner(vt, I_PRESENT, (void *)mi_present, (void **)&g_present_real);
        poner(vt, I_RESET, (void *)mi_reset, (void **)&g_reset_real);
        if (g_buferes) {
            poner(vt, 26 /* CreateVertexBuffer */, (void *)mi_crear_vb, (void **)&g_cvb_real);
            poner(vt, 100 /* SetStreamSource */, (void *)mi_sss, (void **)&g_sss_real);
            poner(vt, 81 /* DrawPrimitive */, (void *)mi_dp, (void **)&g_dp_real);
            poner(vt, 82 /* DrawIndexedPrimitive */, (void *)mi_dip, (void **)&g_dip_real);
        }
        apuntar("  enganchados Present y Reset · tope %d cuadros/s · contador %s · búferes rápidos %s",
                g_tope, g_mostrar ? "sí" : "no", g_buferes ? "sí" : "no");
    }
    return hr;
}

__declspec(dllexport) void *WINAPI Direct3DCreate9(UINT version)
{
    void *fabrica = g_crear ? g_crear(version) : NULL;
    apuntar("Direct3DCreate9(%u) -> %s", version, fabrica ? "ok" : "NULO");
    if (fabrica && g_mejoras) poner(VT(fabrica), 16, (void *)mi_crear_dispositivo, (void **)&g_creardev_real);
    return fabrica;
}

/* ── al cargar ─────────────────────────────────────────────────────────── */
static void leer_ajustes(HMODULE self)
{
    char ruta[MAX_PATH], ini[MAX_PATH], v[32];
    if (!GetModuleFileNameA(self, ruta, MAX_PATH)) return;
    char *barra = strrchr(ruta, '\\');
    if (!barra) return;
    barra[1] = 0;
    lstrcpyA(ini, ruta);
    lstrcatA(ini, "eda_d3d9.ini");
    lstrcpyA(g_ini, ini);
    lstrcpyA(g_log, ruta);
    lstrcatA(g_log, "eda_d3d9.log");
    /* el registro se va sumando (no se pisa al reabrir: la caja negra de la vez anterior queda); pasado
     *   1 MB, el viejo pasa a eda_d3d9.anterior.log */
    WIN32_FILE_ATTRIBUTE_DATA fa;
    if (GetFileAttributesExA(g_log, GetFileExInfoStandard, &fa) && (fa.nFileSizeHigh || fa.nFileSizeLow > (1u << 20))) {
        char viejo[MAX_PATH];
        lstrcpyA(viejo, ruta);
        lstrcatA(viejo, "eda_d3d9.anterior.log");
        MoveFileExA(g_log, viejo, MOVEFILE_REPLACE_EXISTING);
    }
    /* ═══ eda_d3d9.ini POR BLOQUES (12-nov, pedido del dueño del proyecto): LO MÍNIMO (tope de cuadros + server), la CAJA NEGRA, y un
     *   bloque por autor (RUI = los nuestros, HYSTERIA, MAZINO), cada uno con su `activo`. Por defecto: sólo
     *   lo mínimo y la caja negra. [general] mejoras=0 apaga TODO salvo el server, el login y la caja.
     *   ⚠ Las claves viejas ([video] tope_estricto / red_inmediata / anillo_vertices, [compat] letras_32) YA
     *   NO SE LEEN: el .ini es del jugador y así nadie arrastra lo que tenía prendido. Las de [video] que
     *   escribe el launcher (tope_fps, mostrar_fps) siguen donde estaban. ═══ */
    g_mejoras = GetPrivateProfileIntA("general", "mejoras", 1, ini);
    /* LO MÍNIMO */
    g_tope = GetPrivateProfileIntA("video", "tope_fps", 120, ini);
    g_mostrar = GetPrivateProfileIntA("video", "mostrar_fps", 0, ini);
    g_caja = GetPrivateProfileIntA("cajanegra", "activo", 1, ini);
    /* PARCHES DE RUI (los nuestros: MEDICIONES §41–43) */
    g_rui = GetPrivateProfileIntA("rui", "activo", 0, ini);
    g_estricto = g_rui ? GetPrivateProfileIntA("rui", "tope_estricto", 1, ini) : 1;
    g_red = g_rui ? GetPrivateProfileIntA("rui", "red_inmediata", 1, ini) : 0;
    g_buferes = g_rui ? GetPrivateProfileIntA("rui", "anillo_vertices", 0, ini) : 0;
    /* ★ (15-nov) EL ANILLO, PRENDIDO POR DEFECTO con su clave propia [video] anillo (§42–43: el «lag» de la
     *   sala y el lobby es el Lock del búfer de vértices; con el anillo, 120 cuadros/s y la puerta entera).
     *   Estaba apagado desde el 12-nov por ser lo más invasivo (§48), sin una caída medida que fuera suya.
     *   [video] anillo=0 lo apaga; la caja negra dice si una caída es de NUESTRA-d3d9. */
    if (GetPrivateProfileIntA("video", "anillo", 1, ini)) g_buferes = 1;
    g_usar_bombeo = g_rui ? GetPrivateProfileIntA("rui", "bombeo_red", 0, ini) : 0;
    g_rapido = g_rui ? GetPrivateProfileIntA("rui", "backbuffer_rapido", 0, ini) : 0;
    /* PARCHES DE HYSTERIA (PR #6) */
    g_hysteria = GetPrivateProfileIntA("hysteria", "activo", 1, ini);
    g_letras32 = g_hysteria ? GetPrivateProfileIntA("hysteria", "letras_32", 0, ini) : 0;
    g_ping_verde = g_hysteria ? GetPrivateProfileIntA("hysteria", "ping_verde", 0, ini) : 0;   /* ⛔ medido: no cambia el color */
    /* PARCHES DE MAZINO (su arreglo de región, GetCPInfo en 0x7EE13C, ya está ADENTRO del exe: §37) y, ★ desde
     *   el 14-nov, lo que antes hacía Frida (MEDICIONES §57): PRENDIDO por defecto, porque el .ini de cada jugador
     *   no lo pisa el launcher (uno viejo no tiene estas claves) y así llega con la dll nueva. Cada uno se apaga solo. */
    g_mazino = GetPrivateProfileIntA("mazino", "activo", 1, ini);
    g_mz_botones = g_mazino ? GetPrivateProfileIntA("mazino", "botones", 1, ini) : 0;
    g_mz_seleccion = g_mazino ? GetPrivateProfileIntA("mazino", "seleccion_multiple", 1, ini) : 0;
    g_mz_foco = g_mazino ? GetPrivateProfileIntA("mazino", "foco", 1, ini) : 0;
    g_mz_opciones = g_mazino ? GetPrivateProfileIntA("mazino", "opciones", 1, ini) : 0;
    g_mz_atajos = g_mazino ? GetPrivateProfileIntA("mazino", "atajos", 1, ini) : 0;
    /* ★ P2P: que los juegos se encuentren (MEDICIONES §52). Prendido por defecto: sólo arregla lo que
     *   el juego manda roto, y un .ini viejo (el launcher no lo pisa) sin este bloque lo tiene igual */
    g_p2p = GetPrivateProfileIntA("p2p", "activo", 1, ini);
    g_p2p_mac = g_p2p ? GetPrivateProfileIntA("p2p", "mac", 1, ini) : 0;
    g_p2p_ip = g_p2p ? GetPrivateProfileIntA("p2p", "ip_privada", 1, ini) : 0;
    /* ★ la RED INMEDIATA (MEDICIONES §42) pasa a [p2p], prendida (pedido del dueño del proyecto, 13-nov, con el
     *   P2P entre casas andando a 70–90 ms): el juego lee la red UNA vez por cuadro y entre cuadros espera; con
     *   esto la espera se corta apenas llega un paquete. Medido en §42: el ping de la sala, 1 ms a 60 cuadros/s.
     *   (Sólo despierta la espera del tope: no lee ni manda nada por el juego.) [rui] red_inmediata=1 también. */
    if (g_p2p && GetPrivateProfileIntA("p2p", "red_inmediata", 1, ini)) g_red = 1;
    /* (las variables EDA_* mandan sobre el .ini: para medir sin tocarlo) */
    if (GetEnvironmentVariableA("EDA_MEJORAS", v, sizeof(v))) g_mejoras = atoi(v);
    if (GetEnvironmentVariableA("EDA_TOPE_FPS", v, sizeof(v))) g_tope = atoi(v);
    if (GetEnvironmentVariableA("EDA_MOSTRAR_FPS", v, sizeof(v))) g_mostrar = atoi(v);
    if (GetEnvironmentVariableA("EDA_MEDIR_ESCRITURA", v, sizeof(v))) g_medir_escritura = atoi(v);
    if (GetEnvironmentVariableA("EDA_BOMBEO_RED", v, sizeof(v))) g_usar_bombeo = atoi(v);
    if (GetEnvironmentVariableA("EDA_TOPE_ESTRICTO", v, sizeof(v))) g_estricto = atoi(v);
    if (GetEnvironmentVariableA("EDA_RED_INMEDIATA", v, sizeof(v))) g_red = atoi(v);
    if (GetEnvironmentVariableA("EDA_BUFERES_RAPIDOS", v, sizeof(v))) g_buferes = atoi(v);
    if (GetEnvironmentVariableA("EDA_BACKBUFFER_RAPIDO", v, sizeof(v))) g_rapido = atoi(v);
    if (GetEnvironmentVariableA("EDA_LETRAS_32", v, sizeof(v))) g_letras32 = atoi(v);
    /* EDA_OPCIONES=1: la ventana Options de la dll aunque el .ini diga opciones=0 (EDA-DLL-Probar.bat, para probarla
     *   sin perder el panel de Python en el juego de todos los días) */
    if (g_mazino && GetEnvironmentVariableA("EDA_OPCIONES", v, sizeof(v))) g_mz_opciones = atoi(v);
    /* EDA_ATAJOS=0: F10/F11/F12 los sigue haciendo EDA-Atajos.py (el juego de todos los días en la PC de desarrollo) */
    if (g_mazino && GetEnvironmentVariableA("EDA_ATAJOS", v, sizeof(v))) g_mz_atajos = atoi(v);
    if (g_tope < 0) g_tope = 0;
    GetPrivateProfileStringA("red", "server", "", g_server, sizeof(g_server), ini);
    char env[256];                                   /* ⚠ un dominio no entra en los 32 de `v` */
    DWORD n = GetEnvironmentVariableA("EDA_SERVER", env, sizeof(env));
    if (n && n < sizeof(env)) lstrcpyA(g_server, env);
}

BOOL WINAPI DllMain(HINSTANCE self, DWORD razon, LPVOID reservado)
{
    (void)reservado;
    if (razon != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(self);
    /* ⚠ el d3d9 DE VERDAD por ruta absoluta: con "d3d9.dll" a secas Windows encontraría ESTA misma.
     *   En 32 bits sobre Windows de 64, GetSystemDirectory ya devuelve SysWOW64 (el correcto). */
    char sys[MAX_PATH];
    UINT n = GetSystemDirectoryA(sys, MAX_PATH);
    if (!n || n > MAX_PATH - 16) return FALSE;
    lstrcatA(sys, "\\d3d9.dll");
    g_real = LoadLibraryA(sys);
    if (!g_real) return FALSE;
    g_crear = (CREAR9)GetProcAddress(g_real, "Direct3DCreate9");
    if (!g_crear) return FALSE;
    leer_ajustes((HMODULE)self);
    QueryPerformanceFrequency(&g_frec);
    timeBeginPeriod(1);                                          /* Sleep(1) ≈ 1 ms */
    apuntar("──────── eda_d3d9 cargada · el d3d9 real: %s · mejoras %d · tope %d · contador %d · caja negra %d"
            " · RUI %d (estricto %d, red inmediata %d, anillo %d) · HYSTERIA %d (letras 32: %d, ping verde: %d) · MAZINO %d",
            sys, g_mejoras, g_tope, g_mostrar, g_caja, g_rui, g_estricto, g_red, g_buferes, g_hysteria, g_letras32,
            g_ping_verde, g_mazino);
    if (!g_mejoras) apuntar("  [general] mejoras=0: el video y la red del juego quedan como en 2009 (sólo server, login y caja negra)");
    /* ★ la red inmediata: desde YA (el juego puede abrir su socket UDP antes de crear el D3D). Acá
     *   la tabla de importaciones del exe ya está resuelta (los DllMain corren después). */
    if (g_mejoras && g_red && g_tope > 0) {
        g_wsaes_real = (M_WSAES)parchear_iat("WS2_32.dll", "WSAEventSelect", (void *)mi_wsa_event_select);
        apuntar("  red inmediata: %s", g_wsaes_real ? "WSAEventSelect enganchado" : "⚠ no encontré WSAEventSelect en el exe");
    }
    if (g_mejoras && g_letras32) parche_letras();
    if (g_mejoras && g_ping_verde) parche_ping_verde();
    apuntar("  MAZINO %d (botones %d, selección múltiple %d, foco %d, opciones %d, atajos %d) · anillo %d", g_mazino,
            g_mz_botones, g_mz_seleccion, g_mz_foco, g_mz_opciones, g_mz_atajos, g_buferes);
    if (g_mejoras && g_mazino && g_mz_opciones) opc_al_arrancar();   /* antes de que el juego lea autoexec.cfg */
    if (g_mejoras && g_mazino) poner_mazino();
    preparar_linea();                                /* ★ el login del launcher (y puede traer el server) */
    apuntar("  P2P %d (mac %d, ip privada %d)", g_p2p, g_p2p_mac, g_p2p_ip);
    if (g_p2p_mac) parche_mac();
    if (g_p2p_ip) {
        g_ghbn_real = (M_GHBN)parchear_iat("WS2_32.dll", "gethostbyname", (void *)mi_gethostbyname);
        if (!g_ghbn_real) apuntar("  [p2p] ip_privada: ⚠ no encontré gethostbyname en el exe");
    }
    if (g_server[0]) {
        g_connect_real = (M_CONNECT)parchear_iat("WS2_32.dll", "connect", (void *)mi_connect);
        apuntar("  server: %s → %s", g_server, g_connect_real ? "connect enganchado"
                : "⛔ no encontré connect en el exe (¿el EDA.exe con ASProtect? ese va con jugar.py)");
    }
    AddVectoredExceptionHandler(1, mi_excepcion);    /* (1 = antes que los manejadores del juego) */
    return TRUE;
}
