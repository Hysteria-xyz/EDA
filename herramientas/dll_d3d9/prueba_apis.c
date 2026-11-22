/* prueba_apis.c — ★ (21-nov) las pruebas de eda_apis.c sin Windows ni el juego, con el EDA_limpio.exe DE VERDAD:
 *     gcc -std=gnu11 -o /tmp/prueba_apis herramientas/dll_d3d9/prueba_apis.c && /tmp/prueba_apis exe/EDA_limpio.exe
 *   Lee el exe (no lo modifica), lo «carga» en memoria como lo haría Windows (secciones en su lugar), y repara los
 *   sitios de la lista con la misma lógica de la dll: comprueba la trampa, escribe `call [puntero]` y mira que
 *   después de los 6 bytes siga la instrucción que usa el resultado. Con su revés. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#define EDA_APIS_SOLO_DATOS 1
#include "eda_apis.c"

static int ok, mal;
static void chequear(const char *n, int c) { printf("  %s %s\n", c ? "OK " : "MAL", n); if (c) ok++; else mal++; }

static unsigned char *IMG;                           /* la imagen «cargada»: IMG[va - base] */
static unsigned long TAM, SELLO;
static unsigned char *en(unsigned long va) { return IMG + (va - API_EXE_BASE); }
static unsigned long u32(const unsigned char *p) { return p[0] | p[1] << 8 | p[2] << 16 | (unsigned long)p[3] << 24; }

/* el nombre de la función que la tabla de importaciones pone en `casillero` (o NULL): lo que Windows le va a poner */
static unsigned long IMP;                            /* RVA de la tabla de importaciones */
static const char *importada(unsigned long casillero, const char **dll)
{
    for (unsigned char *d = IMG + IMP; u32(d + 12); d += 20) {
        unsigned long oft = u32(d), ft = u32(d + 16);
        for (int i = 0;; i++) {
            unsigned long t = u32(IMG + (oft ? oft : ft) + 4 * i);
            if (!t) break;
            if (API_EXE_BASE + ft + 4 * i == casillero) {
                if (dll) *dll = (const char *)IMG + u32(d + 12);
                return (t & 0x80000000ul) ? "#" : (const char *)IMG + t + 2;
            }
        }
    }
    return NULL;
}

static int cargar(const char *ruta)
{
    FILE *f = fopen(ruta, "rb");
    if (!f) return 0;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *d = malloc(n);
    if (fread(d, 1, n, f) != (size_t)n) return 0;
    fclose(f);
    unsigned long pe = u32(d + 0x3C);
    SELLO = u32(d + pe + 8);
    unsigned secs = d[pe + 6] | d[pe + 7] << 8, opt = d[pe + 20] | d[pe + 21] << 8;
    TAM = u32(d + pe + 24 + 56);
    IMP = u32(d + pe + 24 + 96 + 8);
    IMG = calloc(1, TAM);
    memcpy(IMG, d, 0x400);
    for (unsigned i = 0; i < secs; i++) {
        unsigned char *s = d + pe + 24 + opt + 40 * i;
        unsigned long va = u32(s + 12), rs = u32(s + 16), ro = u32(s + 20);
        if (va + rs > TAM) rs = TAM - va;
        memcpy(IMG + va, d + ro, rs);
    }
    free(d);
    return 1;
}

int main(int argc, char **argv)
{
    const char *exe = argc > 1 ? argv[1] : "exe/EDA_limpio.exe";
    if (!cargar(exe)) { printf("no pude leer %s\n", exe); return 1; }
    chequear("el exe es el conocido (sello y tamaño del PE de la lista)", SELLO == API_EXE_SELLO && TAM == API_EXE_TAMANO);
    int trampas = 0, usan = 0;
    for (int i = 0; i < API_N; i++) {
        unsigned char *p = en(API_SITIOS[i].sitio);
        trampas += api_es_trampa(p, API_SITIOS[i].sitio);
        /* lo que sigue a los 6 bytes usa el resultado de la API: test eax,eax (85 C0) o mov r32,eax (8B xx / 89 45) */
        unsigned char *q = p + 6;
        usan += (q[0] == 0x85 && q[1] == 0xC0) || (q[0] == 0x8B && (q[1] & 0xC7) == 0xC0) || (q[0] == 0x89 && q[1] == 0x45)
                || (q[0] == 0x83 && q[1] == 0x4E) || q[0] == 0xEB;
    }
    char t[160];
    snprintf(t, sizeof(t), "los %d sitios de la lista tienen la trampa EXACTA en el exe (%d)", API_N, trampas);
    chequear(t, trampas == API_N);
    snprintf(t, sizeof(t), "en los %d, después del lugar de 6 bytes sigue código que usa el resultado (%d)", API_N, usan);
    chequear(t, usan == API_N);
    /* reparar como la dll, con punteros de mentira */
    unsigned long base_ptr = 0x10020000;
    for (int i = 0; i < API_N; i++) {
        unsigned char *p = en(API_SITIOS[i].sitio);
        if (api_es_trampa(p, API_SITIOS[i].sitio)) api_instruccion(p, base_ptr + 4 * i);
    }
    int bien = 0;
    for (int i = 0; i < API_N; i++) {
        unsigned char *p = en(API_SITIOS[i].sitio);
        bien += p[0] == 0xFF && p[1] == 0x15 && u32(p + 2) == base_ptr + 4 * i;
    }
    chequear("reparados: cada sitio queda con `call dword ptr [su puntero]` (FF 15 + dirección)", bien == API_N);
    int otra = 0;
    for (int i = 0; i < API_N; i++) otra += api_es_trampa(en(API_SITIOS[i].sitio), API_SITIOS[i].sitio);
    chequear("★ el revés: una vez reparado ya no es trampa (la dll no lo toca dos veces)", otra == 0);
    /* ★ (21-nov, 2ª parte) LAS MAL RESUELTAS: en el sitio está `call [casillero]` y la tabla de importaciones pone en
     *   ese casillero la función EQUIVOCADA (lo que se cayó en EDA-PRUEBA-APIS modo probar, 17:33:47) */
    int malas = 0;
    for (int i = 0; i < API_NM; i++) {
        const API_MAL *m = &API_MALAS[i];
        const char *nom = importada(m->casillero_malo, NULL);
        int esta = api_es_llamada(en(m->sitio), m->casillero_malo) && nom && !strcmp(nom, m->mala)
                   && !api_es_trampa(en(m->sitio), m->sitio);
        malas += esta;
        snprintf(t, sizeof(t), "0x%lX: el exe llama a [0x%lX] = %s (equivocada; la de la CRT es %s)", m->sitio,
                 m->casillero_malo, nom ? nom : "?", m->fn);
        chequear(t, esta);
    }
    /* corregir como la dll: sólo los 4 bytes del casillero */
    for (int i = 0; i < API_NM; i++) {
        unsigned char *p = en(API_MALAS[i].sitio), nuevo[6];
        if (!api_es_llamada(p, API_MALAS[i].casillero_malo)) continue;
        api_instruccion(nuevo, 0x10030000 + 4 * i);
        memcpy(p + 2, nuevo + 2, 4);
    }
    int corr = 0;
    for (int i = 0; i < API_NM; i++) {
        unsigned char *p = en(API_MALAS[i].sitio);
        corr += p[0] == 0xFF && p[1] == 0x15 && u32(p + 2) == 0x10030000ul + 4 * i
                && !api_es_llamada(p, API_MALAS[i].casillero_malo);
    }
    chequear("corregidas: cada una queda con `call [su puntero]` (y ya no se la toma por equivocada: no se toca dos veces)",
             corr == API_NM && malas == API_NM);
    /* ★ el control GENERAL de esta clase de falla: en toda la CRT (0x7DD000…0x7F9000) ningún `call [casillero]` va a
     *   una función interna de ntdll / kernelbase que el código de 2003 no puede haber llamado. Se permiten las que
     *   Windows reenvía con la misma firma (HeapAlloc → RtlAllocateHeap, EnterCriticalSection → Rtl…) y las de
     *   kernelbase con el mismo nombre que la de KERNEL32. Las de API_MALAS ya están corregidas arriba. */
    static const char *permitidas[] = {"RtlAllocateHeap", "RtlReAllocateHeap", "RtlSizeHeap", "RtlFreeHeap",
        "RtlEnterCriticalSection", "RtlLeaveCriticalSection", "RtlDeleteCriticalSection", "RtlInitializeCriticalSection",
        "CreateProcessA", "DeleteFileA", "DuplicateHandle", "EnumSystemLocalesA", "FileTimeToSystemTime", "FindClose",
        "GetCPInfo", "GetCurrentDirectoryA", "GetExitCodeProcess", "GetFileType", "GetModuleFileNameA", "GetModuleHandleA",
        "GetStdHandle", "GetSystemTimeAsFileTime", "RemoveDirectoryA", "SetStdHandle", "WaitForSingleObject", NULL};
    int raras = 0;
    for (unsigned long va = 0x7DD000; va < 0x7F9000; va++) {
        unsigned char *p = en(va);
        if (p[0] != 0xFF || p[1] != 0x15) continue;
        const char *dll = NULL, *nom = importada(u32(p + 2), &dll);
        if (!nom || !dll || (strcasecmp(dll, "ntdll.dll") && strcasecmp(dll, "kernelbase.dll"))) continue;
        int ok_ = 0;
        for (int k = 0; permitidas[k]; k++) ok_ |= !strcmp(nom, permitidas[k]);
        if (!ok_) { raras++; printf("      ⚠ 0x%lX llama a %s!%s\n", va, dll, nom); }
    }
    chequear("en toda la CRT, ninguna otra llamada a una función interna de ntdll/kernelbase (la clase de 0x7F4610)",
             raras == 0);
    chequear("★ el revés: la trampa de un sitio no vale para otro (el destino depende del sitio)",
             !api_es_trampa(en(0x7F4626), 0x7F4627) && !api_es_trampa(en(0x7F4626), 0x7F4625));
    /* la entrada de setlocale (la de la prueba en el juego): el prólogo SEH de la CRT */
    unsigned char *sl = en(0x7E545B);
    chequear("0x7E545B es la entrada de setlocale (6A 14 68 28 B3 8B 00 = el prólogo que mira la dll)",
             sl[0] == 0x6A && sl[1] == 0x14 && sl[2] == 0x68 && u32(sl + 3) == 0x008BB328);
    printf("\n%s (%d bien, %d mal)\n", mal ? "→ ⛔ ALGO FALLA" : "→ TODO BIEN", ok, mal);
    return mal ? 1 : 0;
}
