"""
Pipeline COMPLETO de calificación de una hoja de respuestas de la Copa STEM.

Integra en un solo script:
  - Encabezado del estudiante (Google Vision)         -> nombre, doc, institución, versión
  - Numéricas P1-P4 (Google Vision)                   -> número escrito en columna (a)
  - Selección múltiple P5-P16 (OpenCV, conteo píxeles) -> letra marcada
  - Comparación contra la clave de la versión detectada y cálculo de puntaje.

Uso:
    python src/calificar_hoja.py resultados/paginas_pdf/pagina_001.jpg

Reutiliza las funciones ya calibradas de leer_con_vision.py (Vision) y
leer_respuestas.py (OpenCV). Importarlos NO ejecuta sus main (están protegidos
con if __name__ == "__main__"), pero sí configura credenciales + truststore.
"""

import cv2
import sys
import os
import json

# leer_con_vision configura credenciales/truststore al importarse y expone las
# utilidades de Vision; leer_respuestas expone el conteo de píxeles de OpenCV.
import leer_con_vision as lv
import leer_respuestas as lr
import alinear
import preprocesar_imagen as pi  # realce de rescate para selección en hojas quemadas

from definir_plantilla import (
    NUMERO_PREGUNTAS,
    NUMERO_PREGUNTAS_NUMERICAS,
    FILAS_Y_CENTRO,
    CAMPOS_ENCABEZADO,
)

# Criterios compartidos (no duplicar entre módulos)
from utils import (
    comparar_numerica,
    documento_valido,
    limpiar_texto,
    match_institucion,
    DOC_MIN_DIGITOS,
    DOC_MAX_DIGITOS,
)
from datos_instituciones import INSTITUCIONES

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================
# RUTAS
# ============================================
_DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.normpath(os.path.join(_DIR_SCRIPT, ".."))
RUTA_JSON = os.path.join(_RAIZ, "resultados", "calificacion_completa.json")

# ============================================
# CLAVES DE RESPUESTAS POR VERSIÓN
# ============================================
VERSION_A = {1: "40", 2: "3", 3: "108", 4: "20", 5: "b", 6: "b", 7: "c", 8: "c",
             9: "a", 10: "b", 11: "b", 12: "c", 13: "c", 14: "a", 15: "d", 16: "c"}
VERSION_B = {1: "7", 2: "6", 3: "7500", 4: "63", 5: "b", 6: "a", 7: "b", 8: "c",
             9: "b", 10: "b", 11: "c", 12: "b", 13: "b", 14: "c", 15: "d", 16: "c"}
VERSION_C = {1: "2", 2: "3", 3: "8", 4: "7", 5: "b", 6: "b", 7: "b", 8: "a",
             9: "b", 10: "c", 11: "b", 12: "c", 13: "b", 14: "c", 15: "c", 16: "c"}

CLAVES = {"A": VERSION_A, "B": VERSION_B, "C": VERSION_C}

PUNTOS_NUMERICA = 10
PUNTOS_SELECCION = 5
PUNTAJE_TOTAL = 100

# Selección múltiple: el ganador debe superar al segundo por al menos este
# factor; si no, la marca es dudosa y requiere revisión.
FACTOR_AMBIGUEDAD = 1.5


# ============================================
# LECTURA: ENCABEZADO (filtrado por región de la página completa)
# ============================================
def leer_encabezado(client, imagen, tokens, offset=(0, 0)):
    dx, dy = offset
    mapa = {
        "Nombre completo": "nombre",
        "Numero de identidad": "documento",
        "Institucion educativa": "institucion",
        "Version A/B/C": "version",
    }
    encabezado = {}
    for nombre_campo, region_base in CAMPOS_ENCABEZADO.items():
        clave = mapa.get(nombre_campo, nombre_campo)
        region = alinear.desplazar_region(region_base, dx, dy)

        motivo = None

        if clave == "version":
            # Detección robusta (cae a búsqueda global si la caja no atrapa la letra)
            valor, confianza = lv.detectar_version(tokens, region)
        elif clave == "documento":
            # Lectura robusta: confianza mínima por dígito + validación de formato
            # + respaldo (no sobrescribe lecturas válidas). Devuelve su motivo.
            valor, confianza, motivo = lv.leer_documento(client, imagen, tokens, region)
        else:
            texto, confianza = lv.valor_en_region(tokens, region)
            valor = limpiar_texto(texto) if texto else "no detectado"

        requiere = lv.evaluar_revision(confianza) or (motivo is not None)

        encabezado[clave] = {
            "valor": valor,
            "confianza": round(confianza, 4) if confianza is not None else None,
            "requiere_revision": requiere,
            "motivo": motivo,
        }

    # Fuzzy matching de la institución contra la lista oficial: corrige el texto
    # del OCR al nombre exacto de la base de datos. Guarda el original para
    # auditoría y promueve la revisión si la similitud no es lo bastante alta.
    inst = encabezado.get("institucion")
    if inst is not None:
        original = inst["valor"]
        m = match_institucion(original, INSTITUCIONES)
        inst["valor"] = m["valor"]
        inst["institucion_original"] = original
        inst["similitud"] = m["similitud"]
        if m["requiere_revision"] and original != "no detectado":
            inst["requiere_revision"] = True
            if inst.get("motivo") is None:
                inst["motivo"] = (
                    f"institución sin match fiable en lista oficial "
                    f"(similitud {m['similitud']:.2f}); revisar"
                )
    return encabezado


# ============================================
# LECTURA: NUMÉRICAS P1-P4 (región + respaldo puntual)
# ============================================
def leer_numericas(client, imagen, tokens, offset=(0, 0)):
    # Comparte el híbrido de leer_con_vision: región full-page y, solo si hace
    # falta, un recorte de respaldo para el dígito aislado.
    return {p: lv.leer_numerica(client, imagen, tokens, p, offset)
            for p in range(1, NUMERO_PREGUNTAS_NUMERICAS + 1)}


# ============================================
# LECTURA: SELECCIÓN MÚLTIPLE P5-P16 (OpenCV)
# ============================================
def _conteos_fila(imagen, centro_y, dx):
    """Píxeles de tinta por columna a/b/c/d de una fila (umbral fijo de lr)."""
    conteos = {}
    for i, letra in enumerate(lr.COLUMNAS):
        celda = lr.recortar_celda(imagen, centro_y, i, dx=dx)
        gris = cv2.cvtColor(celda, cv2.COLOR_BGR2GRAY)
        conteos[letra] = int(cv2.countNonZero(lr.binarizar(gris)))
    return conteos


# Piso reducido para el RESCATE sobre la imagen realzada: la marca, ya realzada,
# deja menos píxeles que tinta normal, pero su columna sigue dominando. Solo se
# usa en el reintento (no en la lectura normal) y todo lo recuperado se marca
# para revisión, así que un piso bajo no afecta a las hojas que ya se leen bien.
RESCATE_UMBRAL_MINIMO = 15


def leer_seleccion(imagen, offset=(0, 0)):
    dx, dy = offset
    # La imagen realzada se calcula UNA vez por hoja y solo cuando una fila sale
    # "sin responder" (hoja quemada: el trazo casi no contrasta). En hojas
    # normales ninguna fila legible la necesita, así que no se paga el costo.
    realzada = None
    seleccion = {}
    for pregunta in range(NUMERO_PREGUNTAS_NUMERICAS + 1, NUMERO_PREGUNTAS + 1):
        centro_y = FILAS_Y_CENTRO[pregunta - 1] + dy
        conteos = _conteos_fila(imagen, centro_y, dx)

        # Criterio centralizado en leer_respuestas.clasificar_marca: piso de
        # ruido + ambigüedad por ratio + marca tenue (lápiz claro) -> revisión.
        r = lr.clasificar_marca(conteos)

        # RESCATE: si la fila salió "sin responder", reintenta sobre la imagen
        # realzada (devuelve cuerpo al trazo casi blanco de las hojas quemadas).
        # Lo recuperado SIEMPRE se marca para revisión.
        if r["valor"] == "sin responder":
            if realzada is None:
                realzada = pi.realce_quemado(imagen)
            conteos_r = _conteos_fila(realzada, centro_y, dx)
            r_r = lr.clasificar_marca(conteos_r)
            if r_r["valor"] == "sin responder":
                # Marca ultra tenue: último intento con piso reducido.
                r_r = lr.clasificar_marca(
                    conteos_r, umbral_minimo=RESCATE_UMBRAL_MINIMO)
            if r_r["valor"] != "sin responder":
                conteos = conteos_r
                r = r_r
                r["requiere_revision"] = True
                detalle = f" ({r['motivo']})" if r.get("motivo") else ""
                r["motivo"] = "marca tenue recuperada por realce; verificar" + detalle

        seleccion[pregunta] = {
            "valor": r["valor"],
            "conteos": conteos,
            "ratio": r["ratio"],
            "requiere_revision": r["requiere_revision"],
            "motivo": r["motivo"],
        }
    return seleccion


# ============================================
# CALIFICACIÓN
# ============================================
def calificar(numericas, seleccion, clave):
    comparacion = {}
    puntaje = 0

    for pregunta in range(1, NUMERO_PREGUNTAS_NUMERICAS + 1):
        escrito = numericas[pregunta]["valor"]
        correcta = clave[pregunta]
        es_correcta = comparar_numerica(escrito, correcta)  # normalizada
        pts = PUNTOS_NUMERICA if es_correcta else 0
        puntaje += pts
        comparacion[pregunta] = {
            "tipo": "numerica", "respuesta": escrito, "correcta": correcta,
            "es_correcta": es_correcta, "puntaje": pts,
        }

    for pregunta in range(NUMERO_PREGUNTAS_NUMERICAS + 1, NUMERO_PREGUNTAS + 1):
        marcada = seleccion[pregunta]["valor"]
        correcta = clave[pregunta]
        es_correcta = (marcada == correcta)
        pts = PUNTOS_SELECCION if es_correcta else 0
        puntaje += pts
        comparacion[pregunta] = {
            "tipo": "seleccion", "respuesta": marcada, "correcta": correcta,
            "es_correcta": es_correcta, "puntaje": pts,
        }

    return comparacion, puntaje


def recopilar_revisiones(encabezado, numericas, seleccion):
    """Campos que requieren revisión: baja confianza (Vision) o no leídos."""
    revisiones = []
    etiquetas = {"nombre": "Nombre", "documento": "Documento",
                 "institucion": "Institución", "version": "Versión"}
    for clave, campo in encabezado.items():
        if campo["requiere_revision"]:
            revisiones.append({
                "campo": etiquetas.get(clave, clave),
                "valor": campo["valor"],
                "confianza": campo["confianza"],
                "motivo": campo.get("motivo"),
            })
    for pregunta, campo in numericas.items():
        if campo["requiere_revision"]:
            alt = campo.get("alternativa")
            revisiones.append({
                "campo": f"P{pregunta} (numérica)",
                "valor": campo["valor"],
                "confianza": campo["confianza"],
                "motivo": (f"OCR de respaldo sugiere '{alt}' (se conserva la "
                           f"lectura principal)") if alt else None,
            })
    for pregunta, campo in seleccion.items():
        if campo["requiere_revision"]:
            revisiones.append({
                "campo": f"P{pregunta} (selección)",
                "valor": campo["valor"],
                "confianza": None,
                "motivo": campo.get("motivo"),
            })
    return revisiones


# ============================================
# SALIDA EN CONSOLA
# ============================================
def imprimir_resumen(encabezado, comparacion, puntaje, version, revisiones):
    print("=" * 44)
    print("RESULTADO DE CALIFICACION")
    print("=" * 44)
    print(f"Estudiante: {encabezado['nombre']['valor']}")
    print(f"Documento: {encabezado['documento']['valor']}")
    print(f"Institucion: {encabezado['institucion']['valor']}")
    print(f"Version: {version}")

    print(f"\nNUMERICAS ({PUNTOS_NUMERICA} pts c/u):")
    for p in range(1, NUMERO_PREGUNTAS_NUMERICAS + 1):
        c = comparacion[p]
        marca = "OK" if c["es_correcta"] else "X "
        print(f'P{p}: escribio "{c["respuesta"]}" | correcta "{c["correcta"]}" '
              f'| {marca} {c["puntaje"]} pts')

    print(f"\nSELECCION MULTIPLE ({PUNTOS_SELECCION} pts c/u):")
    for p in range(NUMERO_PREGUNTAS_NUMERICAS + 1, NUMERO_PREGUNTAS + 1):
        c = comparacion[p]
        marca = "OK" if c["es_correcta"] else "X "
        print(f'P{p:<2}: marco "{c["respuesta"]}" | correcta "{c["correcta"]}" '
              f'| {marca} {c["puntaje"]} pts')

    print(f"\nPUNTAJE TOTAL: {puntaje} / {PUNTAJE_TOTAL}")

    print("\nCAMPOS CON BAJA CONFIANZA (requieren revision):")
    if not revisiones:
        print("  (ninguno)")
    for r in revisiones:
        c = r["confianza"]
        c_txt = f"{c:.2f}" if c is not None else "n/d"
        motivo = f" — {r['motivo']}" if r.get("motivo") else ""
        print(f'  - {r["campo"]}: "{r["valor"]}" (confianza: {c_txt}){motivo}')


def evaluar_hoja(client, imagen, version_clave=None):
    """Ejecuta el pipeline completo sobre UNA imagen ya cargada.

    version_clave: versión (A/B/C) cuya clave se usa para calificar. Si es None,
    se usa la versión detectada en la hoja. (El lote pasa la versión del examen;
    el modo individual usa la detectada.)

    Devuelve un dict con todas las piezas + 'salida' (el JSON por hoja).
    Lanza ValueError si la versión a calificar no es A/B/C.
    """
    # Lectura full-page con RESCATE: si la hoja viene quemada/con brillo y Vision
    # apenas detecta texto, se reintenta sobre variantes realzadas (y el negativo
    # solo para Vision). Las hojas que ya se leen bien pasan sin cambios.
    #   - img_vision: imagen de la que provienen los tokens (puede ser negativo).
    #   - img_opencv: mejor imagen NO invertida, para el conteo de marcas y el
    #                 ancla de alineación (ambos asumen tinta oscura sobre claro).
    img_vision, tokens, img_opencv, rescatada = lv.analizar_pagina_robusta(client, imagen)

    # Alineación por ancla: offset (dx,dy) que compensa el desplazamiento de la
    # hoja respecto a la plantilla. Transparente para el resto del pipeline.
    dx, dy, ancla_ok = alinear.calcular_offset(img_opencv)
    offset = (dx, dy)

    encabezado = leer_encabezado(client, img_vision, tokens, offset)
    numericas = leer_numericas(client, img_vision, tokens, offset)
    seleccion = leer_seleccion(img_opencv, offset)

    version_detectada = encabezado["version"]["valor"]
    version_calificacion = version_clave if version_clave else version_detectada
    clave = CLAVES.get(version_calificacion)
    if clave is None:
        raise ValueError(
            f"versión '{version_calificacion}' no reconocida (esperado A/B/C)")

    comparacion, puntaje = calificar(numericas, seleccion, clave)
    revisiones = recopilar_revisiones(encabezado, numericas, seleccion)

    # Si el ancla NO se detectó, no se ajustaron las coordenadas -> toda la hoja
    # es poco fiable: marcarla para revisión.
    if not ancla_ok:
        revisiones.insert(0, {
            "campo": "Alineación",
            "valor": "ancla no detectada",
            "confianza": None,
            "motivo": "no se detectó la banda del encabezado; "
                      "coordenadas sin ajustar (hoja completa a revisar)",
        })

    inst = encabezado["institucion"]
    salida = {
        "encabezado": encabezado,
        "institucion_original": inst.get("institucion_original", inst["valor"]),
        "institucion_corregida": inst["valor"],
        "institucion_similitud": inst.get("similitud"),
        "version_detectada": version_detectada,
        "version_calificacion": version_calificacion,
        "alineacion": {"dx": dx, "dy": dy, "ancla_detectada": ancla_ok},
        "rescate_realce": rescatada,  # True si se realzó por hoja quemada/con brillo
        "respuestas_estudiante": {
            "numericas": {f"pregunta_{p}": numericas[p]["valor"] for p in numericas},
            "seleccion": {f"pregunta_{p}": seleccion[p]["valor"] for p in seleccion},
        },
        "respuestas_correctas": {f"pregunta_{p}": clave[p] for p in clave},
        "comparacion": {f"pregunta_{p}": comparacion[p] for p in comparacion},
        "puntaje_obtenido": puntaje,
        "puntaje_total": PUNTAJE_TOTAL,
        "campos_requieren_revision": revisiones,
    }
    return {
        "encabezado": encabezado,
        "numericas": numericas,
        "seleccion": seleccion,
        "comparacion": comparacion,
        "puntaje": puntaje,
        "revisiones": revisiones,
        "version_detectada": version_detectada,
        "version_calificacion": version_calificacion,
        "salida": salida,
    }


def main():
    if len(sys.argv) != 2:
        print("❌ Uso: python src/calificar_hoja.py <ruta_imagen>")
        sys.exit(1)
    ruta_imagen = sys.argv[1]
    if not os.path.isfile(ruta_imagen):
        print(f"❌ ERROR: No existe la imagen {ruta_imagen}")
        sys.exit(1)

    imagen = cv2.imread(ruta_imagen)
    if imagen is None:
        print(f"❌ ERROR: No se pudo leer la imagen {ruta_imagen}")
        sys.exit(1)

    client = lv.vision.ImageAnnotatorClient(transport="rest")

    try:
        # Modo individual: califica contra la versión DETECTADA en la hoja.
        resultado = evaluar_hoja(client, imagen, version_clave=None)
    except ValueError as e:
        print(f"❌ ERROR: {e}. No se puede calificar.")
        sys.exit(1)

    imprimir_resumen(resultado["encabezado"], resultado["comparacion"],
                     resultado["puntaje"], resultado["version_calificacion"],
                     resultado["revisiones"])

    os.makedirs(os.path.dirname(RUTA_JSON), exist_ok=True)
    with open(RUTA_JSON, "w", encoding="utf-8") as f:
        json.dump(resultado["salida"], f, indent=2, ensure_ascii=False)
    print(f"\n✅ Calificación guardada en: {RUTA_JSON}")

    return resultado["salida"]


if __name__ == "__main__":
    main()
