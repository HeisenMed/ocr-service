"""
Lectura de respuestas de SELECCIÓN MÚLTIPLE (preguntas 5-16) de la hoja
escaneada, usando las coordenadas calibradas en definir_plantilla.py.

Para cada pregunta recorta las 4 celdas (a, b, c, d), cuenta los píxeles
oscuros (la X marcada por el estudiante) y elige la columna con más píxeles.
Si ninguna supera un umbral mínimo, la marca como "sin responder".

NOTA: las preguntas numéricas 1-4 y el encabezado NO se procesan aquí;
esas se resolverán con Google Vision en otra etapa.
"""

import cv2
import numpy as np
import sys
import json
import os

# Reutilizamos las coordenadas calibradas (importar NO ejecuta el dibujo,
# porque definir_plantilla.py protege su main con if __name__ == "__main__")
from definir_plantilla import (
    TABLA_X_INICIO,
    ANCHO_COLUMNA_PREGUNTA,
    ANCHO_COLUMNA_RESPUESTA,
    ALTO_FILA,
    FILAS_Y_CENTRO,
    NUMERO_PREGUNTAS_NUMERICAS,
    NUMERO_PREGUNTAS,
)

# Salida UTF-8 en consolas Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================
# CONFIGURACIÓN
# ============================================
RUTA_IMAGEN = "../resultados/paginas_pdf/pagina_001.jpg"
RUTA_JSON = "../resultados/respuestas_detectadas.json"
RUTA_DEBUG = "../resultados/debug_recortes.jpg"

COLUMNAS = ["a", "b", "c", "d"]

# --- Parámetros ajustables ---
PADDING = 18              # margen interior (px) para no contar los bordes de la celda
# Umbral de binarización: subido de 120 -> 150. Medido sobre marcas reales: una
# X a lápiz CLARO daba solo 2-17 px oscuros a 120 (y se perdía como "sin
# responder"); a 150 da 80-120 px, mientras las celdas vacías se mantienen <60.
# A 170 las vacías empezaban a ensuciarse (>180 px), así que 150 es el punto
# que separa tinta de papel sin meter falsos positivos. Otsu/adaptativo se
# descartaron: en celdas casi uniformes (vacías) disparan miles de px de ruido.
UMBRAL_BINARIZACION = 150
UMBRAL_MINIMO = 60        # piso de ruido: por debajo, la celda se considera vacía
# Por encima de UMBRAL_MINIMO pero por debajo de esto, hay marca pero es tenue
# y se marca para revisión (sin descartarla). Marcas claras dan >150 px.
PISO_CONFIABLE = 130
# El ganador debe superar al segundo por este factor; si no, la marca es dudosa
# (dos casillas con tinta parecida) y se marca para revisión.
FACTOR_AMBIGUEDAD = 1.5
METODO = "fijo"           # "fijo" | "otsu" | "adaptativo"


def binarizar(celda_gris):
    """Devuelve una máscara binaria (255 = píxel oscuro/tinta) según METODO."""
    if METODO == "otsu":
        _, mask = cv2.threshold(
            celda_gris, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
    elif METODO == "adaptativo":
        mask = cv2.adaptiveThreshold(
            celda_gris, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV, 25, 15,
        )
    else:  # "fijo"
        _, mask = cv2.threshold(
            celda_gris, UMBRAL_BINARIZACION, 255, cv2.THRESH_BINARY_INV
        )
    return mask


def clasificar_marca(conteos, umbral_minimo=UMBRAL_MINIMO,
                     piso_confiable=PISO_CONFIABLE):
    """Decide la letra marcada a partir de los conteos de tinta por columna.

    Lógica centralizada (la usan tanto este módulo como calificar_hoja) para no
    duplicar criterios. Devuelve un dict:
        {valor, requiere_revision, motivo, ratio}

    Reglas:
      1) Si el ganador no supera umbral_minimo -> "sin responder".
      2) Si el ganador no supera al segundo por FACTOR_AMBIGUEDAD -> marca
         dudosa: se conserva el ganador pero se marca para revisión.
      3) Si el ganador supera el piso de ruido pero es tenue (< piso_confiable)
         -> se conserva pero se marca para revisión (marca de lápiz claro).

    `umbral_minimo` y `piso_confiable` son parámetros para que el RESCATE de
    hojas quemadas pueda usar un piso más bajo sobre la imagen realzada (las
    marcas, ya realzadas, dan conteos menores que con tinta normal) sin alterar
    el criterio por defecto que usan las hojas normales.
    """
    ordenadas = sorted(conteos.items(), key=lambda kv: kv[1], reverse=True)
    (letra_max, c1), (_, c2) = ordenadas[0], ordenadas[1]

    if c1 < umbral_minimo:
        return {"valor": "sin responder", "requiere_revision": True,
                "motivo": "sin responder", "ratio": None}

    ratio = float("inf") if c2 == 0 else c1 / c2
    ratio_out = None if ratio == float("inf") else round(ratio, 2)

    if ratio < FACTOR_AMBIGUEDAD:
        return {"valor": letra_max, "requiere_revision": True,
                "motivo": f"marca dudosa (ganador {c1} vs segundo {c2}, "
                          f"ratio {ratio:.2f}x < {FACTOR_AMBIGUEDAD}x)",
                "ratio": ratio_out}

    if c1 < piso_confiable:
        return {"valor": letra_max, "requiere_revision": True,
                "motivo": f"marca tenue ({c1} px < {piso_confiable}); revisar",
                "ratio": ratio_out}

    return {"valor": letra_max, "requiere_revision": False,
            "motivo": None, "ratio": ratio_out}


def recortar_celda(imagen, centro_y, indice_columna, dx=0):
    """Recorta la celda (con padding) de una columna a/b/c/d para una fila.

    centro_y ya viene con el offset Y aplicado por quien llama; dx aplica el
    offset X de alineación.
    """
    x_ini = TABLA_X_INICIO + ANCHO_COLUMNA_PREGUNTA + indice_columna * ANCHO_COLUMNA_RESPUESTA + dx
    x_fin = x_ini + ANCHO_COLUMNA_RESPUESTA
    y_ini = centro_y - ALTO_FILA // 2
    y_fin = centro_y + ALTO_FILA // 2
    return imagen[y_ini + PADDING:y_fin - PADDING, x_ini + PADDING:x_fin - PADDING]


def main():
    imagen = cv2.imread(RUTA_IMAGEN)
    if imagen is None:
        print(f"❌ ERROR: No se encontró {RUTA_IMAGEN}")
        return

    print("=" * 60)
    print("LECTURA DE RESPUESTAS — SELECCIÓN MÚLTIPLE (P5-P16)")
    print(f"método={METODO}  padding={PADDING}  "
          f"umbral_bin={UMBRAL_BINARIZACION}  umbral_min={UMBRAL_MINIMO}")
    print("=" * 60)

    respuestas = {}
    debug_filas = []  # para la imagen de depuración

    # Solo selección múltiple: de la primera no-numérica hasta la última pregunta
    for pregunta in range(NUMERO_PREGUNTAS_NUMERICAS + 1, NUMERO_PREGUNTAS + 1):
        centro_y = FILAS_Y_CENTRO[pregunta - 1]

        conteos = {}
        celdas_color = []
        celdas_mask = []
        for i, letra in enumerate(COLUMNAS):
            celda = recortar_celda(imagen, centro_y, i)
            gris = cv2.cvtColor(celda, cv2.COLOR_BGR2GRAY)
            mask = binarizar(gris)
            conteos[letra] = int(cv2.countNonZero(mask))
            celdas_color.append(celda)
            celdas_mask.append(mask)

        # Decisión centralizada (mismo criterio que el pipeline de calificación)
        resultado = clasificar_marca(conteos)
        detectada = resultado["valor"]

        respuestas[f"pregunta_{pregunta}"] = detectada

        detalle = ", ".join(f"{l}={conteos[l]}" for l in COLUMNAS)
        rev = f"  ⚠️ REVISAR — {resultado['motivo']}" if resultado["requiere_revision"] else ""
        print(f"Pregunta {pregunta}: {detectada} ({detalle}){rev}")

        debug_filas.append((pregunta, detectada, conteos, celdas_color))

    # ============================================
    # GUARDAR JSON
    # ============================================
    os.makedirs(os.path.dirname(RUTA_JSON), exist_ok=True)
    with open(RUTA_JSON, "w", encoding="utf-8") as f:
        json.dump(respuestas, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Respuestas guardadas en: {RUTA_JSON}")

    # ============================================
    # IMAGEN DE DEBUG (12 filas x 4 recortes)
    # ============================================
    generar_debug(debug_filas)
    print(f"✅ Debug de recortes guardado en: {RUTA_DEBUG}")

    return respuestas


def generar_debug(debug_filas):
    """Construye una imagen con los 12x4 recortes etiquetados."""
    cw, ch = 150, 90          # tamaño de cada recorte en el lienzo
    margen_izq = 90           # espacio para la etiqueta "P5"
    cab = 22                  # franja superior por celda para el texto
    gap = 8
    fila_h = ch + cab + gap
    ancho = margen_izq + 4 * (cw + gap)
    alto = len(debug_filas) * fila_h + gap

    lienzo = np.full((alto, ancho, 3), 245, dtype="uint8")

    for r, (pregunta, detectada, conteos, celdas) in enumerate(debug_filas):
        y0 = gap + r * fila_h
        # Etiqueta de la pregunta
        cv2.putText(lienzo, f"P{pregunta}", (8, y0 + ch // 2 + cab),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        cv2.putText(lienzo, f"={detectada}", (8, y0 + ch // 2 + cab + 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 120, 0), 2)

        for i, letra in enumerate(COLUMNAS):
            x0 = margen_izq + i * (cw + gap)
            recorte = cv2.resize(celdas[i], (cw, ch))
            lienzo[y0 + cab:y0 + cab + ch, x0:x0 + cw] = recorte

            es_ganadora = (letra == detectada)
            color = (0, 170, 0) if es_ganadora else (120, 120, 120)
            grosor = 3 if es_ganadora else 1
            cv2.rectangle(lienzo, (x0, y0 + cab), (x0 + cw, y0 + cab + ch),
                          color, grosor)
            cv2.putText(lienzo, f"{letra}:{conteos[letra]}",
                        (x0 + 2, y0 + cab - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    cv2.imwrite(RUTA_DEBUG, lienzo)


if __name__ == "__main__":
    main()
