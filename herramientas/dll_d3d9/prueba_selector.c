/* Regresión del punto medido: imagen 14011 sobre botón 14006. */
#include <assert.h>
#include <stdio.h>
#include "eda_selector.h"
typedef struct {unsigned long vt, id; float x1,y1,x2,y2;} Control;
static const Control controles[] = {{0x8AD900,14011,188,185,199,192}, {0x8AD8B8,14006,152,174,192,202}};
static unsigned long elegir(unsigned long escena, float x, float y, int corregir)
{
    for (unsigned i=0;i<sizeof(controles)/sizeof(controles[0]);i++) {
        const Control *c=&controles[i];
        if (corregir && selector_es_flecha(escena,c->vt,c->id)) continue;
        if(x>=c->x1 && x<=c->x2 && y>=c->y1 && y<=c->y2) return c->id;
    }
    return 0;
}
int main(void)
{
    for(int x=188;x<=192;x++) for(int y=185;y<=192;y++) {
        assert(elegir(0x899670,x,y,0)==14011);
        assert(elegir(0x899670,x,y,1)==14006);
        assert(elegir(0x899C20,x,y,1)==14011); /* Stage/combate intacto */
    }
    assert(elegir(0x899670,172,188,1)==14006); /* centro */
    assert(elegir(0x899670,152,188,1)==14006); /* borde opuesto */
    assert(elegir(0x899670,151,188,1)==0);     /* no ampliar el botón */
    assert(elegir(0x899670,195,188,1)==0);     /* sólo flecha: no abrir Stage vecino */
    assert(!selector_es_flecha(0x899670,0x8AD900,13999));
    assert(!selector_es_flecha(0x899670,0x8AD900,14150));
    assert(!selector_es_flecha(0x899670,0x8AD8B8,14006));
    puts("selector: solapamiento, centros, bordes y aislamiento OK");
    return 0;
}
