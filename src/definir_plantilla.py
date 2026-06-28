"""
Script para definir y visualizar la plantilla de coordenadas.
Dibuja rectángulos donde DEBERÍAN estar las celdas de respuestas.
Iteramos hasta que las coordenadas queden perfectas.
"""

import cv2
import sys

# Asegurar salida UTF-8 en consolas Windows (evita UnicodeEncodeError con emojis)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================
# CONFIGURACIÓN
# ============================================
RUTA_IMAGEN = "../resultados/paginas_pdf/pagina_001.jpg"
RUTA_SALIDA = "../resultados/plantilla_visualizada.jpg"

# ============================================
# COORDENADAS DE LA PLANTILLA
# ============================================
# Estas son estimaciones iniciales basadas en una imagen 2480x3309
# Vamos a ajustarlas viendo el resultado

# --- Columnas (eje X) ---
TABLA_X_INICIO = 468  # Borde izquierdo de la columna "Pregunta"
ANCHO_COLUMNA_PREGUNTA = 563  # Columna "Pregunta" (donde dice "1 (10 pts)")
ANCHO_COLUMNA_RESPUESTA = 231  # Cada columna (a), (b), (c), (d)

# --- Filas (eje Y) ---
# El escaneo (Adobe Scan) NO deja las filas equiespaciadas: las primeras
# filas miden ~107px y las últimas ~93px. Por eso un ALTO_FILA uniforme
# acumula desfase. Usamos el centro Y REAL de cada fila (medido sobre la
# imagen 2480x3309) y dibujamos cada celda centrada en él.
FILAS_Y_CENTRO = [
    1304, 1412, 1519, 1626,   # P1-P4  (numéricas)
    1725, 1817, 1912, 2005,   # P5-P8
    2099, 2192, 2287, 2383,   # P9-P12
    2478, 2573, 2666, 2758,   # P13-P16
]
ALTO_FILA = 92  # Altura del rectángulo de cada celda (centrado en FILAS_Y_CENTRO)

# Total de filas: 16 preguntas
NUMERO_PREGUNTAS = len(FILAS_Y_CENTRO)

# Las preguntas 1-4 son numéricas: el estudiante solo escribe en la columna (a).
# Para esas filas dibujamos UN único rectángulo (columna a), sin (b)(c)(d).
NUMERO_PREGUNTAS_NUMERICAS = 4

# ============================================
# CAMPOS DEL ENCABEZADO  (x_ini, y_ini, x_fin, y_fin)
# ============================================
# Regiones donde el estudiante escribe sus datos (a la derecha de cada etiqueta)
# y la casilla de versión del examen. Calibradas sobre la imagen 2480x3309.
# x1 ampliado de 1750 -> 2000: se midió que apellidos largos quedaban fuera del
# ROI por X (p. ej. "Claros" con centro x≈1867 sobre la imagen base). 2000 da
# ~170px de margen y aún excluye la columna de curso/grado (centro x≳2109), que
# no forma parte del nombre. El alto (Y) NO se cambia: las palabras del nombre
# caben en la banda actual (verificado: 0% del nombre real caía fuera por Y).
CAMPOS_ENCABEZADO = {
    "Nombre completo":      (545, 568, 2000, 648),
    "Numero de identidad":  (565, 660, 2000, 730),
    "Institucion educativa": (585, 752, 2000, 822),
    "Version A/B/C":        (1235, 445, 1505, 510),
}

# ============================================
# COLORES
# ============================================
COLOR_PREGUNTA = (255, 0, 0)  # Azul - columna pregunta
COLOR_NUMERICA = (0, 255, 255)  # Amarillo - respuesta numérica (preguntas 1-4)
COLOR_SELECCION = (0, 255, 0)  # Verde - respuesta selección múltiple (5-16)
COLOR_ENCABEZADO = (0, 165, 255)  # Naranja (BGR) - campos del encabezado


def main():
    # ============================================
    # CARGAR IMAGEN
    # ============================================
    imagen = cv2.imread(RUTA_IMAGEN)
    if imagen is None:
        print(f"❌ ERROR: No se encontró {RUTA_IMAGEN}")
        return

    altura, ancho = imagen.shape[:2]
    print(f"✅ Imagen cargada: {ancho} x {altura} px")

    # ============================================
    # DIBUJAR RECTÁNGULOS DE PLANTILLA
    # ============================================
    print(f"\n📐 Dibujando plantilla sobre la imagen...")
    print(f"   Inicio tabla X: x={TABLA_X_INICIO}")
    print(f"   Centros Y de filas: {FILAS_Y_CENTRO[0]} ... {FILAS_Y_CENTRO[-1]} ({NUMERO_PREGUNTAS} filas)")
    print(f"   Ancho columna pregunta: {ANCHO_COLUMNA_PREGUNTA}px")
    print(f"   Ancho columna respuesta: {ANCHO_COLUMNA_RESPUESTA}px")
    print(f"   Alto celda: {ALTO_FILA}px")

    # Dibujar las 16 filas
    for pregunta in range(1, NUMERO_PREGUNTAS + 1):
        # Centro Y real de esta fila -> celda centrada en él (misma línea para
        # la columna "Pregunta" y para las columnas a/b/c/d).
        centro_y = FILAS_Y_CENTRO[pregunta - 1]
        y_ini = centro_y - ALTO_FILA // 2
        y_fin = centro_y + ALTO_FILA // 2

        es_numerica = pregunta <= NUMERO_PREGUNTAS_NUMERICAS

        # Rectángulo de la columna "Pregunta" (donde dice "1 (10 pts)")
        cv2.rectangle(
            imagen,
            (TABLA_X_INICIO, y_ini),
            (TABLA_X_INICIO + ANCHO_COLUMNA_PREGUNTA, y_fin),
            COLOR_PREGUNTA, 4
        )

        # Columnas de respuesta.
        # - Numéricas (P1-P4): SOLO la columna (a), en amarillo.
        # - Selección múltiple (P5-P16): las 4 columnas a/b/c/d, en verde.
        x_actual = TABLA_X_INICIO + ANCHO_COLUMNA_PREGUNTA
        if es_numerica:
            color = COLOR_NUMERICA
            columnas = ['a']
        else:
            color = COLOR_SELECCION
            columnas = ['a', 'b', 'c', 'd']

        for letra in columnas:
            cv2.rectangle(
                imagen,
                (x_actual, y_ini),
                (x_actual + ANCHO_COLUMNA_RESPUESTA, y_fin),
                color, 4
            )
            # Etiqueta de la columna
            cv2.putText(
                imagen,
                letra,
                (x_actual + 10, y_ini + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2
            )
            x_actual += ANCHO_COLUMNA_RESPUESTA

        # Número de la pregunta, centrado verticalmente a la izquierda del rectángulo
        cv2.putText(
            imagen,
            f"P{pregunta}",
            (TABLA_X_INICIO - 60, centro_y + 10),
            cv2.FONT_HERSHEY_SIMPLEX, 1, COLOR_PREGUNTA, 3
        )

    # ============================================
    # DIBUJAR RECTÁNGULOS DEL ENCABEZADO (color naranja)
    # ============================================
    print(f"\n📋 Dibujando campos del encabezado...")
    for nombre_campo, (x_ini, y_ini, x_fin, y_fin) in CAMPOS_ENCABEZADO.items():
        cv2.rectangle(imagen, (x_ini, y_ini), (x_fin, y_fin), COLOR_ENCABEZADO, 4)
        cv2.putText(
            imagen,
            nombre_campo,
            (x_ini, y_ini - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_ENCABEZADO, 2
        )
        print(f"   {nombre_campo}: ({x_ini},{y_ini}) -> ({x_fin},{y_fin})")

    # Guardar
    cv2.imwrite(RUTA_SALIDA, imagen)
    print(f"\n✅ Plantilla visualizada guardada en: {RUTA_SALIDA}")
    print(f"\n💡 Abre el archivo y revisa:")
    print(f"   - Los rectángulos AZULES deben cubrir 'X (XX pts)'")
    print(f"   - Los rectángulos AMARILLOS deben cubrir respuestas numéricas (P1-P4)")
    print(f"   - Los rectángulos VERDES deben cubrir respuestas a/b/c/d (P5-P16)")
    print(f"\n   Si NO coinciden, ajustamos las variables al inicio del archivo:")
    print(f"   - TABLA_X_INICIO → desplaza la tabla en el eje X")
    print(f"   - FILAS_Y_CENTRO → centro Y de cada fila (mueve/ajusta filas)")
    print(f"   - ANCHO_COLUMNA_* → cambian el ancho de las columnas")
    print(f"   - ALTO_FILA → cambia la altura del rectángulo de cada celda")


if __name__ == "__main__":
    main()