/* prueba_traduccion.c — ★ (23-nov) pruebas de eda_traduccion.c sin el juego, con el EDA_limpio.exe DE VERDAD:
 *     gcc -std=gnu11 -Wall -Werror -o /tmp/prueba_traduccion herramientas/dll_d3d9/prueba_traduccion.c \
 *       && /tmp/prueba_traduccion exe/EDA_limpio.exe
 *   Comprueba:
 *     1. Interruptor: apagado por defecto (vacío / "en" / mejoras=0), y sólo idiomas seguros.
 *     2. Normalización y armado de rutas: mayúsculas/minúsculas, separadores, y revés contra traversal (`..`, `:`).
 *     3. Verificación de bytes sobre `EDA_limpio.exe`: PE, los 7 prólogos SolFS, las 16 llamadas `E8` y las 3 cadenas
 *        UTF-16 de `.rdata` (con sus reveses: 1 byte cambiado anula todo).
 *     4. Simulación de redirección (archivo suelto presente → se redirige; ausente → cae a Data.dat).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <direct.h>
#include <sys/stat.h>
#define MKDIR(p) _mkdir(p)
#else
#include <sys/stat.h>
#include <unistd.h>
#define MKDIR(p) mkdir(p, 0755)
#endif

#define EDA_TRADUCCION_SOLO_LOGICA 1
#include "eda_traduccion.c"

static int ok, mal;
static void chequear(const char *n, int c)
{
    printf("  %s %s\n", c ? "OK " : "MAL", n);
    if (c) ok++;
    else mal++;
}

static unsigned char *IMG;
static unsigned long TAM, SELLO;
static unsigned char *en(unsigned long va) { return IMG + (va - TR_EXE_BASE); }
static unsigned long u32(const unsigned char *p)
{
    return (unsigned long)p[0] | ((unsigned long)p[1] << 8)
           | ((unsigned long)p[2] << 16) | ((unsigned long)p[3] << 24);
}

static int cargar_exe(const char *ruta)
{
    FILE *f = fopen(ruta, "rb");
    if (!f) return 0;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (n <= 0x400) { fclose(f); return 0; }
    unsigned char *d = (unsigned char *)malloc((size_t)n);
    if (!d || fread(d, 1, (size_t)n, f) != (size_t)n) { free(d); fclose(f); return 0; }
    fclose(f);
    unsigned long pe = u32(d + 0x3C);
    SELLO = u32(d + pe + 8);
    unsigned secs = (unsigned)(d[pe + 6] | (d[pe + 7] << 8));
    unsigned opt = (unsigned)(d[pe + 20] | (d[pe + 21] << 8));
    TAM = u32(d + pe + 24 + 56);
    IMG = (unsigned char *)calloc(1, TAM);
    if (!IMG) { free(d); return 0; }
    memcpy(IMG, d, 0x400);
    for (unsigned i = 0; i < secs; i++) {
        unsigned char *s = d + pe + 24 + opt + 40u * i;
        unsigned long va = u32(s + 12), rs = u32(s + 16), ro = u32(s + 20);
        if (va >= TAM) continue;
        if (va + rs > TAM) rs = TAM - va;
        if (ro + rs <= (unsigned long)n) memcpy(IMG + va, d + ro, rs);
    }
    free(d);
    return 1;
}

static void a_u16(const char *s, unsigned short *out, int cap)
{
    int i = 0;
    for (; s[i] && i + 1 < cap; i++) out[i] = (unsigned short)(unsigned char)s[i];
    out[i] = 0;
}

static int igual_u16_ascii(const unsigned short *w, const char *s)
{
    int i = 0;
    for (; s[i]; i++) if (w[i] != (unsigned short)(unsigned char)s[i]) return 0;
    return w[i] == 0;
}

static int verificar_todo_exe(unsigned long sello, unsigned long tam)
{
    if (sello != TR_EXE_SELLO || tam != TR_EXE_TAMANO) return 0;
    for (int i = 0; i < TR_NPROLOGOS; i++) {
        if (memcmp(en(TR_PROLOGOS[i].fn), TR_PROLOGOS[i].bytes, 8) != 0) return 0;
    }
    for (int i = 0; i < TR_NSITIOS; i++) {
        if (!tr_es_llamada(en(TR_SITIOS[i].sitio), TR_SITIOS[i].sitio, TR_SITIOS[i].destino)) return 0;
    }
    return 1;
}

/* Simula la decisión de la DLL: devuelve cuántos sitios engancharía (0 si apagado o exe inválido). */
static int simular_instalar(const char *idioma_cfg, int mejoras, unsigned long sello, unsigned long tam)
{
    char idi[16];
    if (!tr_idioma_activo(idioma_cfg, mejoras, idi)) return 0;
    if (!verificar_todo_exe(sello, tam)) return 0;
    return TR_NSITIOS;
}

static int archivo_existe(const char *ruta)
{
    struct stat st;
    return stat(ruta, &st) == 0 && (st.st_mode & S_IFREG);
}

static void u16_a_ascii_slash(const unsigned short *w, char *out, int cap)
{
    int i = 0;
    for (; w[i] && i + 1 < cap; i++) {
        unsigned short c = w[i];
        out[i] = (c == '\\') ? '/' : (char)(c & 0x7F);
    }
    out[i] = 0;
}

int main(int argc, char **argv)
{
    const char *exe = argc > 1 ? argv[1] : "exe/EDA_limpio.exe";

    /* 1. Interruptor y reglas de idioma */
    char idi[16];
    chequear("apagado por defecto: idioma vacío no activa nada", !tr_idioma_activo("", 1, idi));
    chequear("apagado: idioma=NULL no activa nada", !tr_idioma_activo(NULL, 1, idi));
    chequear("apagado: idioma=en / EN no activa nada",
             !tr_idioma_activo("en", 1, idi) && !tr_idioma_activo("EN", 1, idi));
    chequear("apagado: idioma=off / ninguno no activa nada",
             !tr_idioma_activo("off", 1, idi) && !tr_idioma_activo("ninguno", 1, idi));
    chequear("respeta [general] mejoras=0 (ni con idioma=es se activa)", !tr_idioma_activo("es", 0, idi));
    chequear("idioma=es con mejoras=1 activa 'es'",
             tr_idioma_activo("es", 1, idi) && strcmp(idi, "es") == 0);
    chequear("idioma=' ES ' normaliza espacios y mayúsculas a 'es'",
             tr_idioma_activo(" ES ", 1, idi) && strcmp(idi, "es") == 0);
    chequear("★ revés: rechaza idiomas peligrosos (../es, es/x, e, es:1)",
             !tr_idioma_activo("../es", 1, idi) && !tr_idioma_activo("es/x", 1, idi)
             && !tr_idioma_activo("e", 1, idi) && !tr_idioma_activo("es:1", 1, idi));

    /* 2. Normalización y armado de rutas */
    unsigned short in_w[260], out_w[260], base_w[260];
    a_u16("String/International/UIString.xml", in_w, 260);
    chequear("normaliza String/International/UIString.xml → minúsculas con '\\'",
             tr_normalizar_ruta(in_w, out_w, 260)
             && igual_u16_ascii(out_w, "string\\international\\uistring.xml"));

    a_u16("/.\\Image//UI_Image\\International/Shared/top_inven.tga", in_w, 260);
    chequear("normaliza prefijos /.\\ y barras duplicadas",
             tr_normalizar_ruta(in_w, out_w, 260)
             && igual_u16_ascii(out_w, "image\\ui_image\\international\\shared\\top_inven.tga"));

    a_u16("Image\\3D_UI_Image\\critical.dtx", in_w, 260);
    chequear("normaliza rutas 3D LithTech (.dtx)",
             tr_normalizar_ruta(in_w, out_w, 260)
             && igual_u16_ascii(out_w, "image\\3d_ui_image\\critical.dtx"));

    static const char *const malas[] = {
        "", "/", "\\", ".", "..", "../secreto.txt", "string/../../etc/passwd",
        "string/./uistring.xml", "C:\\Windows\\win.ini", "a:b", "a*b.xml", "a?b.xml"
    };
    int todas_rechazadas = 1;
    for (unsigned i = 0; i < sizeof(malas) / sizeof(malas[0]); i++) {
        a_u16(malas[i], in_w, 260);
        if (tr_normalizar_ruta(in_w, out_w, 260)) todas_rechazadas = 0;
    }
    chequear("★ revés: rechaza rutas vacías, traversal (..) y caracteres inválidos", todas_rechazadas);

    a_u16("C:\\Juego\\EDA\\", base_w, 260);
    a_u16("String/International/UIString.xml", in_w, 260);
    chequear("arma ruta completa <base>traducciones\\es\\<rel>",
             tr_armar_ruta(base_w, "es", in_w, out_w, 260)
             && igual_u16_ascii(out_w, "C:\\Juego\\EDA\\traducciones\\es\\string\\international\\uistring.xml"));

    a_u16("C:\\Juego\\EDA", base_w, 260);
    chequear("arma ruta completa aun sin barra final en base_dir",
             tr_armar_ruta(base_w, "es", in_w, out_w, 260)
             && igual_u16_ascii(out_w, "C:\\Juego\\EDA\\traducciones\\es\\string\\international\\uistring.xml"));

    chequear("★ revés: rechaza desborde de búfer pequeño", !tr_armar_ruta(base_w, "es", in_w, out_w, 40));

    /* 3. Verificación contra el EDA_limpio.exe real */
    if (!cargar_exe(exe)) {
        printf("  MAL no pude leer %s\n", exe);
        return 1;
    }
    chequear("el exe es el conocido (PE sello 0x4A858317, imagen 0x5DB000)",
             SELLO == TR_EXE_SELLO && TAM == TR_EXE_TAMANO);

    int pro_ok = 0;
    for (int i = 0; i < TR_NPROLOGOS; i++)
        pro_ok += (memcmp(en(TR_PROLOGOS[i].fn), TR_PROLOGOS[i].bytes, 8) == 0);
    char msg[160];
    snprintf(msg, sizeof(msg), "los %d prólogos de SolFS coinciden byte a byte en el exe (%d)", TR_NPROLOGOS, pro_ok);
    chequear(msg, pro_ok == TR_NPROLOGOS);

    int sit_ok = 0;
    for (int i = 0; i < TR_NSITIOS; i++)
        sit_ok += tr_es_llamada(en(TR_SITIOS[i].sitio), TR_SITIOS[i].sitio, TR_SITIOS[i].destino);
    snprintf(msg, sizeof(msg), "las %d llamadas E8 a SolFS (LithTech + VFS) coinciden exactas (%d)", TR_NSITIOS, sit_ok);
    chequear(msg, sit_ok == TR_NSITIOS);

    chequear("simulación: apagado (vacío / en / mejoras=0) → engancha 0 sitios",
             simular_instalar("", 1, SELLO, TAM) == 0
             && simular_instalar("en", 1, SELLO, TAM) == 0
             && simular_instalar("es", 0, SELLO, TAM) == 0);
    chequear("simulación: idioma=es + mejoras=1 + exe conocido → engancha los 16 sitios",
             simular_instalar("es", 1, SELLO, TAM) == TR_NSITIOS);

    /* Revés: 1 byte distinto en prólogo, llamada o sello del PE → 0 sitios enganchados */
    chequear("★ revés: otro PE (sello distinto) → no engancha nada",
             simular_instalar("es", 1, SELLO ^ 1u, TAM) == 0);
    en(TR_PROLOGOS[0].fn)[0] ^= 0xFFu;
    chequear("★ revés: 1 byte distinto en prólogo SolFSOpenFile → no engancha nada",
             simular_instalar("es", 1, SELLO, TAM) == 0);
    en(TR_PROLOGOS[0].fn)[0] ^= 0xFFu;
    en(TR_SITIOS[1].sitio)[2] ^= 0x01u;
    chequear("★ revés: 1 byte distinto en una llamada E8 → no engancha nada (atómico)",
             simular_instalar("es", 1, SELLO, TAM) == 0);
    en(TR_SITIOS[1].sitio)[2] ^= 0x01u;

    /* 4. Verificación y parcheo de las 3 cadenas UTF-16 de .rdata */
    int cad_ok = 0;
    for (int i = 0; i < TR_NCADENAS; i++) {
        const TR_CADENA_ES *c = &TR_CADENAS_ES[i];
        int ok_i = strlen(c->orig) == strlen(c->nuevo) && tr_coincide_utf16(en(c->va), c->orig);
        cad_ok += ok_i;
    }
    chequear("las 3 cadenas UTF-16 del exe (LV%3d, %dGold, [%s]%s(%dGold)) coinciden y tienen mismo largo",
             cad_ok == TR_NCADENAS);

    for (int i = 0; i < TR_NCADENAS; i++) tr_escribir_utf16(en(TR_CADENAS_ES[i].va), TR_CADENAS_ES[i].nuevo);
    int cad_parchadas = 0;
    for (int i = 0; i < TR_NCADENAS; i++)
        cad_parchadas += tr_coincide_utf16(en(TR_CADENAS_ES[i].va), TR_CADENAS_ES[i].nuevo);
    chequear("tras parchar en memoria: las 3 quedan con el texto ES y NUL exactos", cad_parchadas == TR_NCADENAS);
    chequear("cadenas vecinas intactas ([%s] en 0x89970C y %dCash en 0x899FA4)",
             tr_coincide_utf16(en(0x0089970Cu), "[%s]") && tr_coincide_utf16(en(0x00899FA4u), "%dCash"));

    /* 5. Redirección real sobre archivos temporales: existe → suelto, no existe → Data.dat */
    const char *tmp = "tmp_prueba_traduccion_dir";
    char p1[260], p2[260], p3[260], p4[260], p5[260];
    snprintf(p1, sizeof(p1), "%s/traducciones", tmp);
    snprintf(p2, sizeof(p2), "%s/es", p1);
    snprintf(p3, sizeof(p3), "%s/string", p2);
    snprintf(p4, sizeof(p4), "%s/international", p3);
    snprintf(p5, sizeof(p5), "%s/uistring.xml", p4);
    MKDIR(tmp); MKDIR(p1); MKDIR(p2); MKDIR(p3); MKDIR(p4);
    FILE *f = fopen(p5, "wb");
    if (f) { fputs("<?xml version=\"1.0\" encoding=\"UTF-8\"?>", f); fclose(f); }

    a_u16(tmp, base_w, 260);
    a_u16("String/International/UIString.xml", in_w, 260);
    char resuelta[260];
    int hit = tr_armar_ruta(base_w, "es", in_w, out_w, 260);
    u16_a_ascii_slash(out_w, resuelta, 260);
    chequear("redirección: archivo presente en traducciones/es/ → se lee suelto", hit && archivo_existe(resuelta));

    a_u16("String/International/no_traducido.xml", in_w, 260);
    int miss = tr_armar_ruta(base_w, "es", in_w, out_w, 260);
    u16_a_ascii_slash(out_w, resuelta, 260);
    chequear("★ revés redirección: archivo ausente → no existe en disco (cae a Data.dat)",
             miss && !archivo_existe(resuelta));

    remove(p5);
#ifdef _WIN32
    _rmdir(p4); _rmdir(p3); _rmdir(p2); _rmdir(p1); _rmdir(tmp);
#else
    rmdir(p4); rmdir(p3); rmdir(p2); rmdir(p1); rmdir(tmp);
#endif
    free(IMG);

    printf("\n%s (%d bien, %d mal)\n", mal ? "→ ⛔ ALGO FALLA" : "→ TODO BIEN", ok, mal);
    return mal ? 1 : 0;
}
