"""
Preprocesamiento de imágenes de hojas de respuestas.

Las hojas pueden llegar como foto de cámara (perspectiva, fondo de mesa,
iluminación despareja, rotación) o ya limpias desde Adobe Scan. Este módulo
normaliza CUALQUIER entrada al formato estándar del pipeline:

    - Detecta la hoja blanca (contorno rectangular más grande)
    - Corrige perspectiva a un rectángulo perfecto (si hay hoja sobre fondo)
    - Redimensiona a 2480 x 3309 (tamaño EXACTO para el que están calibradas
      las coordenadas de definir_plantilla.py)
    - Mejora contraste/iluminación (estilo Adobe Scan: fondo blanco, texto negro)

Función principal:  preprocesar(imagen_cv2) -> imagen_cv2 corregida (BGR)

Uso standalone (para depurar):
    python src/preprocesar_imagen.py imagenes_prueba/Imagen1.jpg [salida.jpg]
"""

import cv2
import numpy as np
import sys
import os

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Tamaño estándar (ancho, alto) — el mismo que produce Adobe Scan y para el que
# están calibradas TODAS las coordenadas del proyecto. NO cambiar.
TAMANO_ESTANDAR = (2480, 3309)

# Una hoja se considera "ya a pantalla completa" (no necesita warp) si su
# contorno cubre casi toda la imagen.
UMBRAL_COBERTURA_COMPLETA = 0.95
# El contorno debe cubrir al menos esta fracción para considerarse "la hoja".
UMBRAL_AREA_MINIMA_HOJA = 0.30


def ordenar_esquinas(pts):
    """Ordena 4 puntos como [sup-izq, sup-der, inf-der, inf-izq]."""
    pts = pts.astype("float32")
    suma = pts.sum(axis=1)
    dif = np.diff(pts, axis=1).ravel()
    return np.array([
        pts[np.argmin(suma)],  # sup-izq: menor x+y
        pts[np.argmin(dif)],   # sup-der: menor y-x
        pts[np.argmax(suma)],  # inf-der: mayor x+y
        pts[np.argmax(dif)],   # inf-izq: mayor y-x
    ], dtype="float32")


def detectar_esquinas_hoja(imagen):
    """Devuelve las 4 esquinas de la hoja, o None si no hay un rectángulo claro."""
    h, w = imagen.shape[:2]
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    gris = cv2.GaussianBlur(gris, (5, 5), 0)

    # La hoja es la región clara sobre fondo oscuro -> Otsu.
    _, binaria = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    binaria = cv2.morphologyEx(
        binaria, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25)))

    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return None

    contorno = max(contornos, key=cv2.contourArea)
    if cv2.contourArea(contorno) < UMBRAL_AREA_MINIMA_HOJA * w * h:
        return None  # no hay una hoja suficientemente grande

    # Aproximar a polígono; buscamos 4 vértices.
    peri = cv2.arcLength(contorno, True)
    aprox = None
    for factor in (0.02, 0.01, 0.03, 0.05):
        candidato = cv2.approxPolyDP(contorno, factor * peri, True)
        if len(candidato) == 4:
            aprox = candidato
            break
    if aprox is None:
        return None

    return ordenar_esquinas(aprox.reshape(4, 2))


def _cubre_casi_todo(esquinas, w, h):
    """True si el cuadrilátero ya abarca casi toda la imagen (foto ya limpia)."""
    area_quad = cv2.contourArea(esquinas.astype("float32"))
    return area_quad >= UMBRAL_COBERTURA_COMPLETA * w * h


def corregir_perspectiva(imagen, esquinas, tamano=TAMANO_ESTANDAR):
    """Endereza la hoja a un rectángulo perfecto del tamaño dado."""
    ancho, alto = tamano
    destino = np.array([[0, 0], [ancho - 1, 0],
                        [ancho - 1, alto - 1], [0, alto - 1]], dtype="float32")
    matriz = cv2.getPerspectiveTransform(esquinas, destino)
    return cv2.warpPerspective(imagen, matriz, (ancho, alto))


def mejorar_contraste(imagen, fuerte=True):
    """Normaliza a escala de grises (3 canales). Devuelve BGR.

    fuerte=True (FOTOS): aplana iluminación despareja (divide por fondo
        desenfocado) + CLAHE. Necesario para fotos con sombras.
    fuerte=False (SCANS ya limpios): solo estandariza a gris. La normalización
        fuerte adelgaza/desplaza los trazos finos manuscritos y degrada la
        lectura de Vision en hojas que ya vienen limpias (verificado), así que
        en ese caso NO se toca el contenido.
    """
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)

    if not fuerte:
        return cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR)

    # Aplanar iluminación despareja: dividir por una versión muy desenfocada
    # (estimación del fondo) -> el fondo queda ~blanco uniforme.
    fondo = cv2.GaussianBlur(gris, (0, 0), sigmaX=51)
    normal = cv2.divide(gris, fondo, scale=255)

    # Contraste local adaptativo.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    realzado = clahe.apply(normal)

    return cv2.cvtColor(realzado, cv2.COLOR_GRAY2BGR)


def _aplicar_gamma(gris, gamma):
    """Corrección gamma sobre escala de grises. gamma>1 OSCURECE (realza trazos
    tenues sobre fondo claro); gamma<1 aclara."""
    tabla = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)],
                     dtype="uint8")
    return cv2.LUT(gris, tabla)


def realce_quemado(imagen):
    """Realce AGRESIVO para hojas QUEMADAS (exceso de luz/brillo): el trazo
    manuscrito queda casi tan claro como el papel y ni Vision ni el conteo de
    marcas lo ven. Aplana el fondo, sube el contraste local (CLAHE fuerte) y
    oscurece los tonos medios-altos con gamma>1 para devolverle cuerpo a la
    tinta tenue. MANTIENE la polaridad (tinta oscura sobre fondo claro), así que
    es seguro tanto para Vision como para el conteo de marcas por OpenCV.
    """
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    fondo = cv2.GaussianBlur(gris, (0, 0), sigmaX=51)
    normal = cv2.divide(gris, fondo, scale=255)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    realzado = clahe.apply(normal)
    realzado = _aplicar_gamma(realzado, 1.6)
    return cv2.cvtColor(realzado, cv2.COLOR_GRAY2BGR)


def negativo(imagen):
    """Invierte la imagen (negativo). Útil SOLO para reintentar la LECTURA DE
    TEXTO con Vision en hojas muy claras; NO usar para el conteo de marcas por
    OpenCV (invierte tinta/fondo y rompería el umbral de binarización)."""
    return cv2.bitwise_not(imagen)


def variantes_rescate(imagen):
    """Variantes de realce (NO invertidas) para rescatar hojas mal leídas.

    Devuelve [(nombre, imagen_bgr), ...]. Al mantener la polaridad, cada variante
    sirve tanto para Vision como para el conteo de marcas de OpenCV. El negativo
    NO va aquí: se prueba aparte y solo para Vision (ver analizar_pagina_robusta).
    Ampliar esta lista (otras gammas, otros clipLimit) da más oportunidades de
    rescate a costa de más llamadas a Vision en las páginas difíciles.
    """
    return [("quemado", realce_quemado(imagen))]


def preprocesar(imagen):
    """Normaliza una imagen de hoja al formato estándar del pipeline.

    1) Detecta la hoja y corrige perspectiva (si está sobre un fondo visible).
    2) Si no hay hoja detectable o ya ocupa toda la imagen (foto limpia de
       Adobe Scan), solo redimensiona.
    3) Redimensiona a 2480x3309 y mejora contraste.

    Devuelve la imagen corregida como array OpenCV (BGR). No guarda archivo.
    """
    h, w = imagen.shape[:2]
    esquinas = detectar_esquinas_hoja(imagen)

    if esquinas is not None and not _cubre_casi_todo(esquinas, w, h):
        # Hoja sobre fondo (FOTO) -> enderezar + contraste fuerte.
        corregida = corregir_perspectiva(imagen, esquinas, TAMANO_ESTANDAR)
        return mejorar_contraste(corregida, fuerte=True)

    # Ya viene limpia / a pantalla completa (SCAN) -> redimensionar + suave.
    corregida = cv2.resize(imagen, TAMANO_ESTANDAR)
    return mejorar_contraste(corregida, fuerte=False)


def main():
    if len(sys.argv) < 2:
        print("Uso: python src/preprocesar_imagen.py <imagen> [salida.jpg]")
        sys.exit(1)
    ruta = sys.argv[1]
    imagen = cv2.imread(ruta)
    if imagen is None:
        print(f"❌ ERROR: no se pudo leer {ruta}")
        sys.exit(1)

    print(f"Entrada: {ruta}  ({imagen.shape[1]}x{imagen.shape[0]})")
    esquinas = detectar_esquinas_hoja(imagen)
    if esquinas is None:
        print("Hoja: NO detectada -> solo redimensionar + contraste")
    elif _cubre_casi_todo(esquinas, imagen.shape[1], imagen.shape[0]):
        print("Hoja: ocupa casi toda la imagen (limpia) -> solo redimensionar + contraste")
    else:
        print("Hoja: detectada sobre fondo -> corrección de perspectiva")
        print(f"  Esquinas: {esquinas.tolist()}")

    salida = preprocesar(imagen)
    ruta_salida = sys.argv[2] if len(sys.argv) > 2 else "../resultados/_preprocesada.jpg"
    cv2.imwrite(ruta_salida, salida)
    print(f"Salida: {ruta_salida}  ({salida.shape[1]}x{salida.shape[0]})")


if __name__ == "__main__":
    main()
