"""
Convierte un PDF (o una imagen suelta) en páginas JPG normalizadas que luego
consume el resto del pipeline de OCR.

- PDF  -> cada página se rasteriza a 300 DPI con pdf2image/Poppler.
- JPG/PNG -> se copia tal cual como una única página.

Las imágenes se guardan en resultados/paginas_pdf/ como pagina_001.jpg,
pagina_002.jpg, ... La carpeta se limpia antes de escribir para no mezclar
páginas de un PDF anterior.

Uso:
    python src/procesar_pdf.py imagenes_prueba/PDF1.pdf
    python src/procesar_pdf.py imagenes_prueba/Imagen1.jpg
"""

import cv2
import numpy as np
import sys
import os
import glob

from pdf2image import convert_from_path

# Cada página se normaliza (perspectiva + tamaño estándar + contraste) antes de
# guardarse, para que el pipeline reciba siempre el formato calibrado.
from preprocesar_imagen import preprocesar

# Salida UTF-8 en consolas Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================
# CONFIGURACIÓN
# ============================================
# Carpeta de salida anclada a la ubicación del script (no al directorio actual),
# para que funcione tanto desde la raíz del proyecto como desde src/.
_DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_SALIDA = os.path.join(_DIR_SCRIPT, "..", "resultados", "paginas_pdf")
POPPLER_PATH = r"C:\poppler-26.02.0\Library\bin"
DPI = 300
EXTENSIONES_IMAGEN = (".jpg", ".jpeg", ".png")


def limpiar_carpeta_salida(carpeta):
    """Elimina las pagina_*.jpg previas para no mezclar documentos."""
    os.makedirs(carpeta, exist_ok=True)
    previas = glob.glob(os.path.join(carpeta, "pagina_*.jpg"))
    for archivo in previas:
        os.remove(archivo)
    if previas:
        print(f"🧹 Limpieza: se eliminaron {len(previas)} página(s) anterior(es)")


def ruta_pagina(carpeta, numero):
    """resultados/paginas_pdf/pagina_001.jpg, pagina_002.jpg, ..."""
    return os.path.join(carpeta, f"pagina_{numero:03d}.jpg")


def procesar_pdf(ruta_pdf, carpeta):
    """Rasteriza cada página del PDF a JPG 300 DPI, las PREPROCESA y guarda."""
    print(f"📄 Convirtiendo PDF a {DPI} DPI con Poppler...")
    paginas = convert_from_path(ruta_pdf, dpi=DPI, poppler_path=POPPLER_PATH)

    guardadas = []
    for i, pagina in enumerate(paginas, start=1):
        destino = ruta_pagina(carpeta, i)
        # pdf2image devuelve PIL/RGB -> a BGR de OpenCV -> preprocesar -> guardar.
        cv_img = cv2.cvtColor(np.array(pagina), cv2.COLOR_RGB2BGR)
        cv2.imwrite(destino, preprocesar(cv_img))
        guardadas.append(destino)
    print("🧼 Páginas normalizadas (perspectiva + 2480x3309 + contraste)")
    return guardadas


def procesar_imagen(ruta_img, carpeta):
    """Lee una imagen suelta, la PREPROCESA y la guarda como pagina_001.jpg."""
    print("🖼️  Entrada de imagen: página única")
    imagen = cv2.imread(ruta_img)
    if imagen is None:
        raise ValueError(f"No se pudo leer la imagen: {ruta_img}")
    destino = ruta_pagina(carpeta, 1)
    cv2.imwrite(destino, preprocesar(imagen))
    print("🧼 Página normalizada (perspectiva + 2480x3309 + contraste)")
    return [destino]


def main():
    if len(sys.argv) != 2:
        print("❌ Uso: python src/procesar_pdf.py <ruta_pdf_o_imagen>")
        print("   Ej:  python src/procesar_pdf.py imagenes_prueba/PDF1.pdf")
        sys.exit(1)

    ruta_entrada = sys.argv[1]
    if not os.path.isfile(ruta_entrada):
        print(f"❌ ERROR: No existe el archivo: {ruta_entrada}")
        sys.exit(1)

    extension = os.path.splitext(ruta_entrada)[1].lower()

    print("=" * 60)
    print("PROCESAR PDF / IMAGEN -> páginas JPG")
    print(f"Entrada: {ruta_entrada}")
    print("=" * 60)

    limpiar_carpeta_salida(CARPETA_SALIDA)

    if extension == ".pdf":
        guardadas = procesar_pdf(ruta_entrada, CARPETA_SALIDA)
    elif extension in EXTENSIONES_IMAGEN:
        guardadas = procesar_imagen(ruta_entrada, CARPETA_SALIDA)
    else:
        print(f"❌ ERROR: Extensión no soportada '{extension}'. "
              f"Use PDF, JPG o PNG.")
        sys.exit(1)

    # ============================================
    # RESUMEN
    # ============================================
    print(f"\n✅ {len(guardadas)} página(s) procesada(s):")
    for destino in guardadas:
        img = cv2.imread(destino)
        if img is not None:
            alto, ancho = img.shape[:2]
            print(f"   {os.path.basename(destino)}: {ancho} x {alto} px")
        else:
            print(f"   {os.path.basename(destino)}: (no se pudo releer)")


if __name__ == "__main__":
    main()
