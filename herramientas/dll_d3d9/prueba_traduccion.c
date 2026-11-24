/* prueba_traduccion.c — ★ (23-nov) pruebas de eda_traduccion.c sin el juego, con el EDA_limpio.exe DE VERDAD:
 *     python herramientas/dll_d3d9/compilar.py --generar-traduccion herramientas/dll_d3d9/eda_traduccion_datos.h
 *     gcc -std=gnu11 -Wall -Werror -o /tmp/prueba_traduccion herramientas/dll_d3d9/prueba_traduccion.c \
 *       && /tmp/prueba_traduccion exe/EDA_limpio.exe .
 *   Comprueba:
 *     1. Interruptor: apagado si vacío / "en" / mejoras=0, y sólo idiomas seguros.
 *     2. Normalización y armado de rutas: mayúsculas/minúsculas, separadores, y revés contra traversal (`..`, `:`).
 *     3. Verificación de bytes sobre `EDA_limpio.exe`: PE, los 7 prólogos SolFS, las 16 llamadas `E8` y las 3 cadenas
 *        UTF-16 de `.rdata` (con sus reveses: 1 byte cambiado anula todo).
 *     4. Traducción embebida: búsqueda, lectura byte a byte con seek/pos/read contra `traduccion/es/`, prioridad
 *        suelto → embebido → Data.dat, y reveses (archivo no embebido cae a Data.dat, otro idioma devuelve NULL).
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

    /* 0. ★ (24-nov) las pantallas panorámicas: qué variante se elige para cada resolución */
    chequear("panorámico: 16:9 (1280×720 … 3840×2160, también 1366×768) → 1066",
             tr_ancho_elegir(1280, 720) == 1066 && tr_ancho_elegir(1366, 768) == 1066 && tr_ancho_elegir(1600, 900) == 1066
             && tr_ancho_elegir(1920, 1080) == 1066 && tr_ancho_elegir(2560, 1440) == 1066 && tr_ancho_elegir(3840, 2160) == 1066);
    chequear("panorámico: 16:10 (1440×900, 1680×1050, 1920×1200) → 960",
             tr_ancho_elegir(1440, 900) == 960 && tr_ancho_elegir(1680, 1050) == 960 && tr_ancho_elegir(1920, 1200) == 960);
    chequear("panorámico: 21:9 (2560×1080) → 1066 (centrado, con franjas)", tr_ancho_elegir(2560, 1080) == 1066);
    chequear("★ revés: 4:3 y 5:4 (1024×768, 800×600, 1280×1024) → el original (0)",
             !tr_ancho_elegir(1024, 768) && !tr_ancho_elegir(800, 600) && !tr_ancho_elegir(1280, 1024));
    chequear("★ revés: tamaños sin sentido (0, negativos) → el original", !tr_ancho_elegir(0, 600) && !tr_ancho_elegir(1920, 0)
             && !tr_ancho_elegir(-5, 600));

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

    /* 4b. Diagnóstico de glifos FreeType: filtro de caracteres y bytes exactos del exe */
    chequear("filtro diag_glifos selecciona ñ, Ñ, ó, n, ü y excluye otras letras (a, o, A, ¡)",
             tr_es_glifo_diag(0x00F1u) && tr_es_glifo_diag(0x00D1u) && tr_es_glifo_diag(0x00F3u)
             && tr_es_glifo_diag(0x006Eu) && tr_es_glifo_diag(0x00FCu)
             && strcmp(tr_nombre_glifo_diag(0x00F1u), "ñ") == 0
             && strcmp(tr_nombre_glifo_diag('a'), "?") == 0
             && !tr_es_glifo_diag('a') && !tr_es_glifo_diag('o') && !tr_es_glifo_diag('A') && !tr_es_glifo_diag(0x00A1u));
    chequear("sitio CreateGlyph (0x771FF1 → 0x770A00) y prólogos CreateGlyph/FT_Load_Glyph coinciden en el exe",
             tr_es_llamada(en(TR_SITIO_CREATE_GLYPH), TR_SITIO_CREATE_GLYPH, TR_FN_CREATE_GLYPH)
             && memcmp(en(TR_FN_CREATE_GLYPH), TR_PROLOGO_CREATE_GLYPH, 8) == 0
             && memcmp(en(TR_FN_FT_LOAD_GLYPH), TR_PROLOGO_FT_LOAD, 8) == 0);
    en(TR_SITIO_CREATE_GLYPH)[1] ^= 0x01u;
    chequear("★ revés diag_glifos: 1 byte cambiado en 0x771FF1 anula el gancho",
             !tr_es_llamada(en(TR_SITIO_CREATE_GLYPH), TR_SITIO_CREATE_GLYPH, TR_FN_CREATE_GLYPH));
    en(TR_SITIO_CREATE_GLYPH)[1] ^= 0x01u;

    /* 5. Redirección y traducción embebida: prioridad suelto → embebido → Data.dat */
    const char *raiz_repo = argc > 2 ? argv[2] : ".";
    char ruta_check[320];
    snprintf(ruta_check, sizeof(ruta_check), "%s/traduccion/es/string/international/uistring.xml", raiz_repo);
    if (!archivo_existe(ruta_check)) raiz_repo = "../..";

    chequear("embebidos en la DLL: hay 5 XML para idioma=es y 0 para idioma desconocido",
             tr_contar_embebidos("es") == 5 && tr_contar_embebidos("zz") == 0 && tr_contar_embebidos("en") == 0);

    static const char *const rutas_es[5] = {
        "Data/Scenario/String/International/Chapter1_string.xml",
        "String/International/Err_String.xml",
        "String/International/MapNameAndExplainString.xml",
        "String/International/NameAndExplainString.xml",
        "/.\\String//International\\UIString.xml",
    };
    int emb_ok = 0;
    for (int i = 0; i < 5; i++) {
        a_u16(rutas_es[i], in_w, 260);
        if (!tr_normalizar_ruta(in_w, out_w, 260)) continue;
        const TR_EMBEBIDO *e = tr_buscar_embebido("es", out_w);
        if (!e || !e->datos || e->tam == 0u) continue;
        char rel_slash[260], ruta_disco[400];
        u16_a_ascii_slash(out_w, rel_slash, 260);
        snprintf(ruta_disco, sizeof(ruta_disco), "%s/traduccion/es/%s", raiz_repo, rel_slash);
        FILE *fd = fopen(ruta_disco, "rb");
        if (!fd) continue;
        fseek(fd, 0, SEEK_END);
        long sz = ftell(fd);
        fseek(fd, 0, SEEK_SET);
        if (sz != (long)e->tam) { fclose(fd); continue; }
        unsigned char *disk = (unsigned char *)malloc((size_t)sz);
        unsigned char *leido = (unsigned char *)malloc((size_t)sz);
        if (!disk || !leido || fread(disk, 1, (size_t)sz, fd) != (size_t)sz) {
            free(disk); free(leido); fclose(fd); continue;
        }
        fclose(fd);
        /* Leer por bloques usando tr_mem_read / tr_mem_seek como lo hace SolFS */
        unsigned long pos = 0u, outp = 0u, tot = 0u;
        int ok_io = (tr_mem_seek(e->tam, &pos, 0, 2u, &outp) == 0 && outp == e->tam)
                    && (tr_mem_seek(e->tam, &pos, 0, 0u, &outp) == 0 && outp == 0u);
        while (ok_io && tot < e->tam) {
            unsigned long n = 0u;
            if (tr_mem_read(e->datos, e->tam, &pos, leido + tot, 1024u, &n) != 0 || n == 0u) { ok_io = 0; break; }
            tot += n;
        }
        unsigned long eof_n = 99u;
        if (ok_io && tr_mem_read(e->datos, e->tam, &pos, leido, 16u, &eof_n) == 0 && eof_n == 0u
            && tot == e->tam && pos == e->tam && memcmp(leido, disk, (size_t)sz) == 0) {
            /* Seek relativo (FILE_CURRENT) y negativo desde el final (FILE_END) */
            unsigned char tail[8], tail_disk[8];
            unsigned long n2 = 0u;
            if (tr_mem_seek(e->tam, &pos, -8L, 2u, &outp) == 0 && outp == e->tam - 8u
                && tr_mem_read(e->datos, e->tam, &pos, tail, 8u, &n2) == 0 && n2 == 8u
                && memcmp(tail, disk + sz - 8, 8) == 0) {
                memcpy(tail_disk, disk + 4, 8);
                if (tr_mem_seek(e->tam, &pos, 0, 0u, &outp) == 0
                    && tr_mem_seek(e->tam, &pos, 4L, 1u, &outp) == 0 && outp == 4u
                    && tr_mem_read(e->datos, e->tam, &pos, tail, 8u, &n2) == 0 && n2 == 8u
                    && memcmp(tail, tail_disk, 8) == 0)
                    emb_ok++;
            }
        }
        free(disk);
        free(leido);
    }
    chequear("los 5 XML embebidos coinciden byte a byte con traduccion/es/ (vía seek/pos/read)", emb_ok == 5);

    unsigned long p_inv = 0u, o_inv = 0u;
    chequear("★ revés seek en memoria: origen inválido (-24) y posición negativa (-1) se rechazan",
             tr_mem_seek(100u, &p_inv, 0, 9u, &o_inv) == -24 && tr_mem_seek(100u, &p_inv, -5L, 0u, &o_inv) == -1);

    a_u16("String/International/no_traducido.xml", in_w, 260);
    tr_normalizar_ruta(in_w, out_w, 260);
    chequear("★ revés embebido: archivo no embebido devuelve NULL (cae a Data.dat)",
             tr_buscar_embebido("es", out_w) == NULL);

    a_u16("String/International/UIString.xml", in_w, 260);
    tr_normalizar_ruta(in_w, out_w, 260);
    chequear("★ revés embebido: mismo archivo con otro idioma ('en'/'fr') devuelve NULL",
             tr_buscar_embebido("en", out_w) == NULL && tr_buscar_embebido("fr", out_w) == NULL);

    /* Prioridad real: 1) suelto en disco → 2) embebido → 3) Data.dat */
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
    unsigned short norm_w[260];
    tr_normalizar_ruta(in_w, norm_w, 260);
    chequear("prioridad 1 (suelto > embebido): archivo presente en traducciones/es/ gana sobre el embebido",
             hit && archivo_existe(resuelta) && tr_buscar_embebido("es", norm_w) != NULL);

    a_u16("String/International/Err_String.xml", in_w, 260);
    hit = tr_armar_ruta(base_w, "es", in_w, out_w, 260);
    u16_a_ascii_slash(out_w, resuelta, 260);
    tr_normalizar_ruta(in_w, norm_w, 260);
    chequear("prioridad 2 (embebido): ausente en traducciones/es/ pero presente embebido → se sirve embebido",
             hit && !archivo_existe(resuelta) && tr_buscar_embebido("es", norm_w) != NULL);

    a_u16("String/International/no_traducido.xml", in_w, 260);
    int miss = tr_armar_ruta(base_w, "es", in_w, out_w, 260);
    u16_a_ascii_slash(out_w, resuelta, 260);
    tr_normalizar_ruta(in_w, norm_w, 260);
    chequear("★ revés prioridad 3 (Data.dat): ausente en disco y no embebido → cae a Data.dat",
             miss && !archivo_existe(resuelta) && tr_buscar_embebido("es", norm_w) == NULL);

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
