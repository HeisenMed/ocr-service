"""
Procesa un LOTE completo: un PDF (o imagen) con varias hojas de respuestas,
calificando cada página contra la clave de la versión indicada.

Uso:
    python src/procesar_lote.py imagenes_prueba/PDF1.pdf B
    python src/procesar_lote.py imagenes_prueba/Imagen1.jpg A

Flujo:
  1) Convierte el PDF/imagen a páginas JPG (reutiliza procesar_pdf.py).
  2) Para cada página ejecuta el pipeline completo (reutiliza calificar_hoja.py)
     calificando contra la versión pasada por argumento.
  3) Guarda el resultado individual de cada hoja y un resumen del lote.
"""

import cv2
import sys
import os
import glob
import json

import procesar_pdf as pp
import calificar_hoja as ch
import leer_con_vision as lv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================
# RUTAS
# ============================================
_DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.normpath(os.path.join(_DIR_SCRIPT, ".."))
CARPETA_HOJAS = os.path.join(_RAIZ, "resultados", "hojas")          # resultados por hoja
RUTA_RESUMEN = os.path.join(_RAIZ, "resultados", "resumen_lote.json")

EXTENSIONES_IMAGEN = (".jpg", ".jpeg", ".png")


def convertir_a_paginas(ruta_entrada):
    """Convierte el PDF/imagen a páginas JPG y devuelve las rutas ordenadas.

    procesar_pdf YA preprocesa cada página (perspectiva + 2480x3309 + contraste)
    antes de guardarla, así que las rutas que devolvemos apuntan a imágenes ya
    normalizadas y listas para calificar. No volver a preprocesar aquí.
    """
    pp.limpiar_carpeta_salida(pp.CARPETA_SALIDA)
    extension = os.path.splitext(ruta_entrada)[1].lower()
    if extension == ".pdf":
        pp.procesar_pdf(ruta_entrada, pp.CARPETA_SALIDA)
    elif extension in EXTENSIONES_IMAGEN:
        pp.procesar_imagen(ruta_entrada, pp.CARPETA_SALIDA)
    else:
        raise ValueError(f"Extensión no soportada: '{extension}' (use PDF/JPG/PNG)")
    return sorted(glob.glob(os.path.join(pp.CARPETA_SALIDA, "pagina_*.jpg")))


def etiqueta_corta(campo):
    """'P1 (numérica)' -> 'P1'; 'Documento' -> 'Documento'."""
    return campo.split(" ", 1)[0] if campo.startswith("P") else campo


def main():
    if len(sys.argv) != 3:
        print("❌ Uso: python src/procesar_lote.py <ruta_pdf_o_imagen> <version A|B|C|AUTO>")
        print("   AUTO = cada hoja se califica con la versión detectada por Vision.")
        sys.exit(1)

    ruta_entrada = sys.argv[1]
    version = sys.argv[2].strip().upper()

    if not os.path.isfile(ruta_entrada):
        print(f"❌ ERROR: No existe el archivo {ruta_entrada}")
        sys.exit(1)
    if version != "AUTO" and version not in ch.CLAVES:
        print(f"❌ ERROR: versión '{version}' inválida (esperado A, B, C o AUTO)")
        sys.exit(1)

    auto = (version == "AUTO")

    print("=" * 60)
    print(f"PROCESAR LOTE — versión {'AUTO (detectada por hoja)' if auto else version}")
    print(f"Entrada: {ruta_entrada}")
    print("=" * 60)

    # 1) Convertir a páginas
    try:
        paginas = convertir_a_paginas(ruta_entrada)
    except ValueError as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)
    if not paginas:
        print("❌ ERROR: no se generaron páginas.")
        sys.exit(1)
    print(f"📄 {len(paginas)} página(s) a procesar.\n")

    # 2) Calificar cada página
    client = lv.vision.ImageAnnotatorClient(transport="rest")
    os.makedirs(CARPETA_HOJAS, exist_ok=True)
    # Borrar hoja_*.json de un lote anterior: si el lote previo era más grande,
    # sus hojas sobrantes contaminarían el Excel (filas de estudiantes ajenos).
    for viejo in glob.glob(os.path.join(CARPETA_HOJAS, "hoja_*.json")):
        os.remove(viejo)

    resultados = []
    fallos = []
    # En AUTO, version_clave=None -> evaluar_hoja usa la versión detectada.
    version_clave = None if auto else version

    for i, ruta_pag in enumerate(paginas, start=1):
        imagen = cv2.imread(ruta_pag)
        if imagen is None:
            print(f"⚠️  Página {i}: no se pudo leer {ruta_pag}")
            fallos.append({"pagina": i, "error": "no se pudo leer la imagen"})
            continue

        print(f"  Procesando página {i}/{len(paginas)} ...")
        try:
            r = ch.evaluar_hoja(client, imagen, version_clave=version_clave)
        except Exception as e:
            # P. ej. versión no detectada (A/B/C) en modo AUTO, u otro error.
            print(f"  ⚠️  Página {i} FALLÓ: {e}")
            fallos.append({"pagina": i, "error": str(e)})
            continue

        # Guardar resultado individual de la hoja
        ruta_hoja = os.path.join(CARPETA_HOJAS, f"hoja_{i:03d}.json")
        with open(ruta_hoja, "w", encoding="utf-8") as f:
            json.dump(r["salida"], f, indent=2, ensure_ascii=False)

        enc = r["encabezado"]
        campos_revision = [etiqueta_corta(rev["campo"]) for rev in r["revisiones"]]
        resultados.append({
            "pagina": i,
            "nombre": enc["nombre"]["valor"],
            "documento": enc["documento"]["valor"],
            "institucion": enc["institucion"]["valor"],
            "version_detectada": r["version_detectada"],
            "puntaje": r["puntaje"],
            "puntaje_total": ch.PUNTAJE_TOTAL,
            "campos_revision": campos_revision,
            "respuestas": r["salida"]["respuestas_estudiante"],
        })

    # 3) Estadísticas del lote
    puntajes = [res["puntaje"] for res in resultados]
    total = len(resultados)
    estadisticas = {
        "promedio": round(sum(puntajes) / total, 2) if total else 0,
        "maximo": max(puntajes) if puntajes else 0,
        "minimo": min(puntajes) if puntajes else 0,
        # nº de hojas que tienen al menos un campo marcado para revisión
        "total_requieren_revision": sum(1 for res in resultados if res["campos_revision"]),
        "hojas_con_fallo": len(fallos),
    }

    resumen = {
        "version": version,
        "total_hojas": total,
        "resultados": resultados,
        "fallos": fallos,
        "estadisticas": estadisticas,
    }
    os.makedirs(os.path.dirname(RUTA_RESUMEN), exist_ok=True)
    with open(RUTA_RESUMEN, "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)

    # 4) Tabla en consola
    imprimir_tabla(resultados, fallos, estadisticas)
    print(f"\n✅ Resultados por hoja en: {CARPETA_HOJAS}")
    print(f"✅ Resumen del lote en: {RUTA_RESUMEN}")


def imprimir_tabla(resultados, fallos, estadisticas):
    print("\n" + "=" * 86)
    print(f"{'Pag':<4}| {'Nombre':<26}| {'Documento':<12}| {'Ver':<4}| "
          f"{'Puntaje':<8}| {'Rev':<4}| Campos a revisar")
    print("-" * 86)
    for res in resultados:
        nombre = (res["nombre"] or "")[:25]
        doc = (res["documento"] or "")[:11]
        ver = res["version_detectada"] or "?"
        puntaje = f"{res['puntaje']}/{res['puntaje_total']}"
        n_rev = len(res["campos_revision"])
        campos = ", ".join(res["campos_revision"]) if res["campos_revision"] else "-"
        print(f"{res['pagina']:<4}| {nombre:<26}| {doc:<12}| {ver:<4}| "
              f"{puntaje:<8}| {n_rev:<4}| {campos}")
    for f in fallos:
        print(f"{f['pagina']:<4}| {'*** FALLÓ ***':<26}| {'-':<12}| {'-':<4}| "
              f"{'-':<8}| {'-':<4}| {f['error']}")
    print("-" * 86)
    print(f"Hojas OK: {len(resultados)}  |  Fallos: {len(fallos)}  |  "
          f"Promedio: {estadisticas['promedio']}  |  "
          f"Máx: {estadisticas['maximo']}  |  Mín: {estadisticas['minimo']}  |  "
          f"Hojas con revisión: {estadisticas['total_requieren_revision']}")


if __name__ == "__main__":
    main()
