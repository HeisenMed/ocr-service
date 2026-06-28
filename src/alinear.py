"""
Alineación por anclas: compensa el desplazamiento (offset) de cada hoja respecto
a la plantilla calibrada, usando la BANDA OSCURA del encabezado de la tabla
("Pregunta | (a) | (b) | (c) | (d)") como referencia estable.

NO reemplaza la plantilla: solo calcula un (dx, dy) por hoja que el pipeline
suma a TODAS las coordenadas (filas, columnas, encabezado).

Función principal:
    calcular_offset(imagen) -> (dx, dy, ok)
        ok=False si no se detectó el ancla (el pipeline usa offset (0,0) y marca
        la hoja para revisión).
"""

import cv2
import numpy as np

# ============================================================
# REFERENCIA (medida sobre la imagen de calibración, 2480x3309)
# Banda oscura del encabezado: centro Y y borde X izquierdo.
# Estos valores se obtuvieron corriendo detectar_banda() sobre el scan base.
# ============================================================
# Medidos con detectar_banda() sobre el scan base PDF1 (preprocesado).
REF_BANDA_Y = 1203   # centro Y de la banda oscura
REF_BANDA_X = 543    # borde izquierdo del relleno oscuro de la banda

# Parámetros de detección
UMBRAL_OSCURO = 110          # un píxel es "oscuro" si gris < este valor
Y_BUSQUEDA = (600, 2100)     # franja vertical donde puede estar la banda
X_BUSQUEDA = (350, 2100)     # franja horizontal de análisis
FRAC_FILA_BANDA = 0.45       # una fila es "de banda" si >45% de su ancho es oscuro
FRAC_COL_BANDA = 0.50        # una col cuenta para el borde si >50% de la banda es oscura
ALTO_MIN_BANDA = 25          # alto mínimo (px) de la banda para considerarla válida
# Si el offset supera esto, lo consideramos detección dudosa (probable error).
OFFSET_MAX = 400


def detectar_banda(imagen):
    """Devuelve (y_centro, x_izquierdo) de la banda oscura, o None si no la halla."""
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen
    h, w = gris.shape[:2]

    y0, y1 = Y_BUSQUEDA[0], min(Y_BUSQUEDA[1], h)
    x0, x1 = X_BUSQUEDA[0], min(X_BUSQUEDA[1], w)
    sub = gris[y0:y1, x0:x1]
    ancho = x1 - x0

    oscuro = (sub < UMBRAL_OSCURO).astype(np.uint8)
    filas_oscuras = oscuro.sum(axis=1) > FRAC_FILA_BANDA * ancho

    # Buscar la racha contigua más larga de filas "de banda".
    mejor_ini = mejor_fin = ini = None
    mejor_len = 0
    for i, es_banda in enumerate(filas_oscuras):
        if es_banda:
            if ini is None:
                ini = i
            if i - ini + 1 > mejor_len:
                mejor_len = i - ini + 1
                mejor_ini, mejor_fin = ini, i
        else:
            ini = None

    if mejor_ini is None or mejor_len < ALTO_MIN_BANDA:
        return None

    y_centro = y0 + (mejor_ini + mejor_fin) // 2

    # Borde X izquierdo del relleno oscuro dentro de la banda.
    banda = oscuro[mejor_ini:mejor_fin + 1, :]
    alto_banda = mejor_fin - mejor_ini + 1
    cols = banda.sum(axis=0) > FRAC_COL_BANDA * alto_banda
    indices = np.where(cols)[0]
    if indices.size == 0:
        return None
    x_izq = x0 + int(indices[0])

    return (y_centro, x_izq)


def calcular_offset(imagen):
    """Calcula (dx, dy, ok) respecto a la plantilla calibrada.

    ok=False si no se detecta el ancla o el offset es absurdamente grande;
    en ese caso devuelve (0, 0, False) y el pipeline debe marcar revisión.
    """
    ancla = detectar_banda(imagen)
    if ancla is None:
        return (0, 0, False)
    y_centro, x_izq = ancla
    dy = y_centro - REF_BANDA_Y
    dx = x_izq - REF_BANDA_X
    if abs(dx) > OFFSET_MAX or abs(dy) > OFFSET_MAX:
        return (0, 0, False)
    return (dx, dy, True)


def desplazar_region(region, dx, dy):
    """(x0,y0,x1,y1) -> desplazada por (dx,dy)."""
    x0, y0, x1, y1 = region
    return (x0 + dx, y0 + dy, x1 + dx, y1 + dy)


if __name__ == "__main__":
    import sys
    img = cv2.imread(sys.argv[1])
    print(f"Imagen: {sys.argv[1]} ({img.shape[1]}x{img.shape[0]})")
    ancla = detectar_banda(img)
    print(f"Banda detectada (y_centro, x_izq): {ancla}")
    print(f"Offset (dx, dy, ok): {calcular_offset(img)}")
