
"""
Lectura con Google Cloud Vision de:
  - Preguntas NUMÉRICAS P1-P4 (el número escrito en la columna (a))
  - ENCABEZADO del estudiante (nombre, documento, institución, versión)

Usa las coordenadas calibradas en definir_plantilla.py para recortar cada
región y enviarla a la API document_text_detection (optimizada para escritura
a mano). La selección múltiple P5-P16 se resuelve aparte en leer_respuestas.py.
"""

import cv2
import numpy as np
import sys
import os
import re
import json

# ============================================
# RUTAS (ancladas a la ubicación del script)
# ============================================
_DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.normpath(os.path.join(_DIR_SCRIPT, ".."))

RUTA_CREDENCIALES = os.path.join(_RAIZ, "credentials.json")
RUTA_IMAGEN = os.path.join(_RAIZ, "resultados", "paginas_pdf", "pagina_001.jpg")
RUTA_JSON = os.path.join(_RAIZ, "resultados", "vision_detectado.json")
RUTA_DEBUG = os.path.join(_RAIZ, "resultados", "debug_vision_recortes.jpg")

# Configurar credenciales ANTES de crear el cliente de Vision
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = RUTA_CREDENCIALES

# Esta máquina tiene interceptación TLS (antivirus/proxy con una CA raíz propia
# instalada en el almacén de Windows pero ausente de certifi). truststore hace
# que el módulo ssl de Python use el almacén de certificados de Windows, de modo
# que las conexiones HTTPS confíen en esa CA. Debe inyectarse antes de crear el
# cliente. Por eso usamos el transporte REST de Vision (gRPC/BoringSSL no puede
# aprovechar el almacén de Windows).
import truststore  # noqa: E402
truststore.inject_into_ssl()

from google.cloud import vision  # noqa: E402  (debe ir tras setear la env var)

from definir_plantilla import (  # noqa: E402
    TABLA_X_INICIO,
    ANCHO_COLUMNA_PREGUNTA,
    ANCHO_COLUMNA_RESPUESTA,
    ALTO_FILA,
    FILAS_Y_CENTRO,
    NUMERO_PREGUNTAS_NUMERICAS,
    CAMPOS_ENCABEZADO,
)

import preprocesar_imagen as pi  # noqa: E402  (realce de rescate para hojas quemadas)

from utils import (  # noqa: E402
    limpiar_texto,
    documento_valido,
    DOC_MIN_DIGITOS,
    DOC_MAX_DIGITOS,
)

# Salida UTF-8 en consolas Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- Parámetros ---
# Sin recorte interior: preparar_numerica() ya rodea el dígito con un borde
# blanco. Un padding >0 llegaba a cortar dígitos que tocan el borde de la celda
# (p. ej. el '1' de P1), haciendo que Vision no lo detectara.
PADDING_NUMERICA = 0

# Umbral de confianza: por debajo de esto, el campo se marca para revisión manual.
# Calibrado sobre escritura a MANO: los nombres legibles y bien transcritos por
# Vision puntúan de forma natural entre ~0.70 y ~0.85 (la letra manuscrita rara
# vez supera eso), así que 0.85 marcaba a revisión decenas de campos correctos.
# Por debajo de 0.70 sí aparece ruido OCR real (letras inventadas, dígitos
# pegados al nombre). El documento NO depende solo de este promedio: tiene su
# propia validación por dígito (UMBRAL_CONF_DIGITO) y de formato, que siguen
# atrapando los casos dudosos aunque el promedio sea alto.
UMBRAL_CONFIANZA = 0.70

# Confianza MÍNIMA por dígito en el documento. Un solo dígito muy dudoso queda
# oculto en el promedio (medido: documento real 6052540 leído como 5052540, con
# el primer dígito a conf 0.49 mientras el promedio subía a 0.89). Los dígitos
# bien leídos estaban en 0.83-0.99, así que 0.6 separa limpiamente el dígito malo.
UMBRAL_CONF_DIGITO = 0.6


def _confianza_promedio(respuesta):
    """Promedio de confidence de todos los símbolos de un document_text_detection.
    Devuelve None si no hay símbolos."""
    fta = respuesta.full_text_annotation
    confs = []
    for page in fta.pages:
        for block in page.blocks:
            for parrafo in block.paragraphs:
                for palabra in parrafo.words:
                    for simbolo in palabra.symbols:
                        confs.append(simbolo.confidence)
    return sum(confs) / len(confs) if confs else None


def detectar_texto(client, recorte_bgr, fallback_text_detection=False):
    """Envía un recorte (BGR de OpenCV) a Vision.

    Devuelve (texto, confianza), donde confianza es el promedio de confidence
    de los símbolos (0..1) o None si no está disponible (p. ej. cuando se usa
    el fallback text_detection, que no reporta confidence por símbolo).

    document_text_detection es el mejor para escritura a mano densa, pero a veces
    devuelve vacío con caracteres MUY aislados (un solo dígito). En ese caso, si
    fallback_text_detection=True, reintenta con text_detection.
    """
    ok, buffer = cv2.imencode(".jpg", recorte_bgr)
    if not ok:
        return "", None
    image = vision.Image(content=buffer.tobytes())

    respuesta = client.document_text_detection(image=image)
    if respuesta.error.message:
        raise RuntimeError(f"Vision API: {respuesta.error.message}")
    if respuesta.full_text_annotation and respuesta.full_text_annotation.text.strip():
        return respuesta.full_text_annotation.text.strip(), _confianza_promedio(respuesta)

    if fallback_text_detection:
        respuesta2 = client.text_detection(image=image)
        if respuesta2.error.message:
            raise RuntimeError(f"Vision API: {respuesta2.error.message}")
        if respuesta2.text_annotations:
            # text_detection no expone confidence por símbolo de forma fiable.
            return respuesta2.text_annotations[0].description.strip(), None

    return "", None


def evaluar_revision(confianza):
    """True si el campo requiere revisión manual (confianza baja o desconocida)."""
    return confianza is None or confianza < UMBRAL_CONFIANZA


# ============================================================
# DETECCIÓN OPTIMIZADA: UNA sola llamada por hoja
# ============================================================
# En vez de recortar y enviar cada campo (8 llamadas/hoja), enviamos la página
# COMPLETA una vez y luego filtramos por coordenadas las palabras detectadas que
# caen dentro de cada rectángulo calibrado. Para 1300+ hojas esto pasa de
# ~10.400 llamadas a ~1.300.

def extraer_tokens(respuesta):
    """Convierte la respuesta full-page en una lista de palabras con su caja.

    Cada token: {texto, cx, cy, h, confs} donde (cx, cy) es el centro del
    bounding box de la palabra, h su altura (px) y confs las confidence de sus
    símbolos. La altura permite agrupar palabras en líneas con una tolerancia
    proporcional al tamaño del texto (en vez de un grid vertical fijo).
    """
    tokens = []
    fta = respuesta.full_text_annotation
    for page in fta.pages:
        for block in page.blocks:
            for parrafo in block.paragraphs:
                for palabra in parrafo.words:
                    texto = "".join(s.text for s in palabra.symbols)
                    if not texto:
                        continue
                    vs = palabra.bounding_box.vertices
                    xs = [v.x for v in vs]
                    ys = [v.y for v in vs]
                    tokens.append({
                        "texto": texto,
                        "cx": sum(xs) / len(xs),
                        "cy": sum(ys) / len(ys),
                        "h": max(ys) - min(ys),
                        "confs": [s.confidence for s in palabra.symbols],
                    })
    return tokens


def analizar_pagina(client, imagen):
    """UNA llamada document_text_detection sobre la imagen completa.
    Devuelve la lista de tokens (palabras con caja y confianza)."""
    ok, buffer = cv2.imencode(".jpg", imagen)
    if not ok:
        raise RuntimeError("No se pudo codificar la imagen para Vision")
    image = vision.Image(content=buffer.tobytes())
    respuesta = client.document_text_detection(image=image)
    if respuesta.error.message:
        raise RuntimeError(f"Vision API: {respuesta.error.message}")
    return extraer_tokens(respuesta)


# Si una página devuelve MENOS de estos tokens, se considera una lectura pobre
# (típico de hojas quemadas por exceso de luz, donde el trazo casi no contrasta)
# y se intenta rescatarla con realce. Una hoja normal entrega muchos más tokens
# (etiquetas impresas + 16 filas + escritura), así que este umbral no dispara en
# páginas que ya se leen bien. Subirlo intenta el rescate en más páginas (más
# llamadas a Vision); bajarlo lo reserva para las más extremas.
UMBRAL_TOKENS_RESCATE = 40


def analizar_pagina_robusta(client, imagen):
    """Analiza la página y, si la lectura es POBRE, la rescata con realce.

    Capacidad ADITIVA: una hoja que ya se lee bien (>= UMBRAL_TOKENS_RESCATE
    tokens) toma el camino normal, con UNA sola llamada y sin tocar la imagen.
    Solo cuando la lectura base es escasa (hoja quemada/con brillo) se reintenta
    sobre variantes realzadas y, por último, sobre el NEGATIVO, quedándose con la
    que más texto recupere.

    Devuelve (img_vision, tokens, img_opencv, rescatada):
      - img_vision:  imagen cuyos `tokens` se devuelven (PUEDE ser un negativo).
      - tokens:      tokens detectados en img_vision.
      - img_opencv:  mejor imagen NO invertida; para el conteo de marcas de
                     selección por OpenCV, que asume tinta oscura sobre claro
                     (un negativo rompería ese conteo).
      - rescatada:   True si se adoptó una variante realzada (lectura difícil).
    """
    tokens = analizar_pagina(client, imagen)
    if len(tokens) >= UMBRAL_TOKENS_RESCATE:
        return imagen, tokens, imagen, False

    # 1) Variantes realzadas NO invertidas (sirven para Vision y para OpenCV).
    mejor_img, mejor_tokens = imagen, tokens
    for _, variante in pi.variantes_rescate(imagen):
        t = analizar_pagina(client, variante)
        if len(t) > len(mejor_tokens):
            mejor_img, mejor_tokens = variante, t

    # 2) Negativo: último recurso SOLO para Vision (no se usa en OpenCV).
    negativo = pi.negativo(mejor_img)
    t_neg = analizar_pagina(client, negativo)
    if len(t_neg) > len(mejor_tokens):
        return negativo, t_neg, mejor_img, True

    return mejor_img, mejor_tokens, mejor_img, (mejor_img is not imagen)


def agrupar_en_lineas(tokens_dentro, tol_y=None):
    """Agrupa palabras en líneas de lectura y las ordena izquierda→derecha.

    Antes se usaba un grid fijo `round(cy/25)`: una línea LIGERAMENTE INCLINADA
    (frecuente en escritura a mano) cruzaba la frontera del grid y se partía en
    dos buckets, revolviendo el orden de las palabras (p. ej. el nombre
    'Mathias Alejandro Lopez Moret' salía como 'Alejandro Lopez Moret ... Mathias').

    Aquí agrupamos por CERCANÍA vertical con una tolerancia proporcional a la
    altura del texto (robusta a inclinación y a distintos tamaños de letra):
    dos palabras pertenecen a la misma línea si la diferencia de sus centros Y
    es menor que `tol_y`. Devuelve una lista de líneas; cada línea es una lista
    de tokens ya ordenada por X, y las líneas van de arriba hacia abajo.
    """
    if not tokens_dentro:
        return []
    if tol_y is None:
        # ~70% de la altura mediana de palabra: suficiente para tolerar la
        # inclinación de un renglón, sin fusionar dos renglones distintos.
        alturas = sorted(t.get("h", 0) for t in tokens_dentro)
        h_med = alturas[len(alturas) // 2] or 40
        tol_y = max(15, 0.7 * h_med)

    ordenados = sorted(tokens_dentro, key=lambda t: t["cy"])
    lineas = [[ordenados[0]]]
    for t in ordenados[1:]:
        # Comparar contra el centro Y MEDIO de la línea en curso (no solo el
        # último token) para no encadenar una escalera de palabras inclinadas.
        cy_linea = sum(u["cy"] for u in lineas[-1]) / len(lineas[-1])
        if abs(t["cy"] - cy_linea) <= tol_y:
            lineas[-1].append(t)
        else:
            lineas.append([t])
    for linea in lineas:
        linea.sort(key=lambda t: t["cx"])
    return lineas


def texto_y_confs_en_region(tokens, region):
    """Reconstruye el texto de una región y devuelve (texto, confs).

    `confs` es la lista de confidence por SÍMBOLO de las palabras incluidas, lo
    que permite calcular tanto el promedio como el MÍNIMO (un solo dígito muy
    dudoso queda oculto en el promedio pero salta en el mínimo).
    """
    x0, y0, x1, y1 = region
    dentro = [t for t in tokens if x0 <= t["cx"] <= x1 and y0 <= t["cy"] <= y1]
    lineas = agrupar_en_lineas(dentro)
    texto = " ".join(t["texto"] for linea in lineas for t in linea).strip()
    confs = [c for t in dentro for c in t["confs"]]
    return texto, confs


def valor_en_region(tokens, region):
    """Concatena las palabras cuyo CENTRO cae dentro de region=(x0,y0,x1,y1).

    Reconstruye el orden de lectura agrupando por líneas (tolerancia vertical
    proporcional al tamaño del texto) y ordenando cada línea por X. Devuelve
    (texto, confianza) donde confianza es el promedio de las confidence de los
    símbolos de las palabras incluidas (None si no cae ninguna).
    """
    texto, confs = texto_y_confs_en_region(tokens, region)
    confianza = sum(confs) / len(confs) if confs else None
    return texto, confianza


def region_celda_numerica(pregunta, offset=(0, 0)):
    """Rectángulo (x0,y0,x1,y1) de la columna (a) de una pregunta numérica,
    con el offset de alineación aplicado."""
    dx, dy = offset
    centro_y = FILAS_Y_CENTRO[pregunta - 1] + dy
    x0 = TABLA_X_INICIO + ANCHO_COLUMNA_PREGUNTA + dx  # columna (a) = índice 0
    x1 = x0 + ANCHO_COLUMNA_RESPUESTA
    y0 = centro_y - ALTO_FILA // 2
    y1 = centro_y + ALTO_FILA // 2
    return (x0, y0, x1, y1)


def _leer_recorte_numerico(client, imagen, pregunta, offset):
    """Lectura de respaldo: recorte de la celda + escalado, vía Vision.
    Devuelve (valor, confianza). conf suele ser None (usa text_detection)."""
    recorte = preparar_numerica(recorte_celda_numerica(imagen, pregunta, offset))
    texto2, conf2 = detectar_texto(client, recorte, fallback_text_detection=True)
    return solo_digitos(texto2), conf2


def leer_numerica(client, imagen, tokens, pregunta, offset=(0, 0)):
    """Lee UNA numérica desde los tokens de la página completa.

    Los dígitos manuscritos AISLADOS son el punto débil de la detección
    full-page (un '1' puede no detectarse; un '8' puede partirse en '8'+'00').
    El recorte de respaldo (escalado + INTER_LINEAR) ayuda en esos casos.

    POLÍTICA DE RESPALDO (corrige el bug histórico en que el respaldo
    SOBRESCRIBÍA una lectura de región correcta, p. ej. '128' conf 0.84 -> '728'):

      - Región VACÍA  -> el respaldo es la única fuente: se usa si aporta dígito.
      - Región CON valor pero baja confianza -> el respaldo solo CORROBORA:
          * si coincide con la región -> lectura corroborada (quita revisión).
          * si discrepa -> se CONSERVA la región (primaria) y se anota la
            'alternativa'; queda marcada para revisión (no se sobrescribe).
      - Región CON valor y confianza alta -> no se llama al respaldo.
    """
    texto, conf = valor_en_region(tokens, region_celda_numerica(pregunta, offset))
    valor = solo_digitos(texto)
    fallback = False
    alternativa = None
    requiere = evaluar_revision(conf)

    if valor == "no detectado":
        valor2, conf2 = _leer_recorte_numerico(client, imagen, pregunta, offset)
        if valor2 != "no detectado":
            valor, conf, fallback = valor2, conf2, True
            requiere = evaluar_revision(conf)
    elif requiere:
        valor2, _ = _leer_recorte_numerico(client, imagen, pregunta, offset)
        if valor2 == valor:
            # Dos métodos independientes coinciden -> lectura corroborada.
            requiere = False
        elif valor2 != "no detectado":
            # Discrepan: conservar la región y dejar constancia de la alternativa.
            alternativa = valor2

    return {
        "valor": valor,
        "confianza": round(conf, 4) if conf is not None else None,
        "requiere_revision": requiere,
        "fallback": fallback,
        "alternativa": alternativa,
    }


def recorte_celda_numerica(imagen, pregunta, offset=(0, 0)):
    """Recorta la columna (a) de una pregunta numérica, con padding y offset."""
    x0, y0, x1, y1 = region_celda_numerica(pregunta, offset)
    p = PADDING_NUMERICA
    return imagen[y0 + p:y1 - p, x0 + p:x1 - p]


def leer_documento(client, imagen, tokens, region):
    """Lee el documento de identidad de forma robusta. Devuelve (valor, conf, motivo).

    Mejoras sobre la lectura cruda (solo_digitos(valor_en_region)):
      1) Confianza MÍNIMA por dígito, no solo el promedio: un dígito muy dudoso
         (conf < UMBRAL_CONF_DIGITO) marca el documento para revisión aunque el
         promedio sea alto.
      2) Validación de formato (4-12 dígitos).
      3) Respaldo: si la región queda vacía o con formato inválido, intenta un
         recorte escalado; solo lo adopta si DA un formato válido que la región
         no tenía (no sobrescribe una lectura válida a ciegas).

    `region` ya viene desplazada por el offset de alineación (igual que en el
    resto del encabezado).
    """
    texto, confs = texto_y_confs_en_region(tokens, region)
    valor = solo_digitos(texto)
    conf_prom = sum(confs) / len(confs) if confs else None
    conf_min = min(confs) if confs else None
    motivo = None

    # Respaldo solo cuando la región no dio un documento válido.
    if valor == "no detectado" or not documento_valido(valor):
        x0, y0, x1, y1 = region
        recorte = preparar_numerica(imagen[y0:y1, x0:x1])
        texto2, _ = detectar_texto(client, recorte, fallback_text_detection=True)
        valor2 = solo_digitos(texto2)
        if valor2 != "no detectado" and documento_valido(valor2) and not documento_valido(valor):
            valor = valor2
            motivo = "documento recuperado por OCR de respaldo; revisar"

    if not documento_valido(valor):
        motivo = (f"formato inválido (se esperan {DOC_MIN_DIGITOS}-"
                  f"{DOC_MAX_DIGITOS} dígitos)")
    elif conf_min is not None and conf_min < UMBRAL_CONF_DIGITO:
        motivo = f"dígito de baja confianza (mín {conf_min:.2f} < {UMBRAL_CONF_DIGITO})"

    return valor, conf_prom, motivo


def preparar_numerica(recorte_bgr):
    """Escala el recorte y le añade un borde blanco. Vision lee mejor los
    dígitos cuando son grandes pero conservan margen/contexto alrededor
    (un recorte ajustado a la tinta, sin márgenes, empeora la detección)."""
    # INTER_LINEAR (no CUBIC): el cúbico mete artefactos de "ringing" alrededor
    # de trazos finos (un '1') y Vision deja de detectarlos.
    grande = cv2.resize(recorte_bgr, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR)
    grande = cv2.copyMakeBorder(grande, 50, 50, 50, 50,
                                cv2.BORDER_CONSTANT, value=(255, 255, 255))
    return grande


def solo_digitos(texto):
    """Deja únicamente dígitos. Devuelve 'no detectado' si no hay ninguno."""
    digitos = re.sub(r"\D", "", texto)
    return digitos if digitos else "no detectado"


def extraer_version(texto):
    """Busca la letra de versión A/B/C en el texto detectado."""
    m = re.search(r"[ABC]", texto.upper())
    return m.group(0) if m else "no detectado"


def detectar_version(tokens, region):
    """Detecta la versión A/B/C de forma robusta. Devuelve (letra, confianza).

    1) Intenta en la región calibrada (rápido, lo normal).
    2) Si falla (la hoja está desplazada y la caja no atrapa la letra), busca en
       TODA la página un token 'Versión'/'Version' y la letra A/B/C contigua a su
       derecha en la misma línea. Robustece ante variación de encuadre.
    """
    texto, conf = valor_en_region(tokens, region)
    letra = extraer_version(texto)
    if letra != "no detectado":
        return letra, conf

    for t in tokens:
        if t["texto"].lower().startswith("versi"):
            candidatos = [
                u for u in tokens
                if abs(u["cy"] - t["cy"]) < 30          # misma línea
                and 0 < u["cx"] - t["cx"] < 400          # a la derecha, cerca
                and u["texto"].strip().upper() in ("A", "B", "C")
            ]
            if candidatos:
                u = min(candidatos, key=lambda c: c["cx"])
                conf_u = sum(u["confs"]) / len(u["confs"]) if u["confs"] else None
                return u["texto"].strip().upper(), conf_u

    return "no detectado", None


def main():
    if not os.path.isfile(RUTA_CREDENCIALES):
        print(f"❌ ERROR: No se encontró credentials.json en {RUTA_CREDENCIALES}")
        sys.exit(1)

    imagen = cv2.imread(RUTA_IMAGEN)
    if imagen is None:
        print(f"❌ ERROR: No se encontró la imagen {RUTA_IMAGEN}")
        sys.exit(1)

    print("=" * 60)
    print("LECTURA CON GOOGLE VISION — numéricas P1-P4 + encabezado")
    print("=" * 60)

    # Transporte REST (no gRPC) para poder usar el almacén de certificados de
    # Windows vía truststore en entornos con interceptación TLS.
    client = vision.ImageAnnotatorClient(transport="rest")

    # UNA sola llamada a Vision con la página completa.
    tokens = analizar_pagina(client, imagen)

    debug_items = []  # (titulo, recorte, texto_detectado)

    # ============================================
    # ENCABEZADO (filtrado por región, sin más llamadas)
    # ============================================
    encabezado = {}
    mapa_campos = {
        "Nombre completo": "nombre",
        "Numero de identidad": "documento",
        "Institucion educativa": "institucion",
        "Version A/B/C": "version",
    }
    for nombre_campo, region in CAMPOS_ENCABEZADO.items():
        clave = mapa_campos.get(nombre_campo, nombre_campo)

        if clave == "version":
            valor, confianza = detectar_version(tokens, region)
        elif clave == "documento":
            texto, confianza = valor_en_region(tokens, region)
            valor = solo_digitos(texto)
        else:
            # nombre / institución: quitar etiqueta impresa residual
            texto, confianza = valor_en_region(tokens, region)
            valor = limpiar_texto(texto) if texto else "no detectado"

        encabezado[clave] = {
            "valor": valor,
            "confianza": round(confianza, 4) if confianza is not None else None,
            "requiere_revision": evaluar_revision(confianza),
        }
        x0, y0, x1, y1 = region
        debug_items.append((f"{clave}: {valor}", imagen[y0:y1, x0:x1], valor))

    # ============================================
    # NUMÉRICAS P1-P4 (filtrado por región)
    # ============================================
    numericas = {}
    for pregunta in range(1, NUMERO_PREGUNTAS_NUMERICAS + 1):
        entrada = leer_numerica(client, imagen, tokens, pregunta)
        numericas[f"pregunta_{pregunta}"] = entrada
        x0, y0, x1, y1 = region_celda_numerica(pregunta)
        sufijo = " [respaldo]" if entrada["fallback"] else ""
        debug_items.append((f"P{pregunta}: {entrada['valor']}{sufijo}",
                            imagen[y0:y1, x0:x1], entrada["valor"]))

    # ============================================
    # RESUMEN EN CONSOLA
    # ============================================
    def _fmt(campo):
        c = campo["confianza"]
        marca = "  ⚠️ REVISAR" if campo["requiere_revision"] else ""
        c_txt = f"{c:.2f}" if c is not None else "n/d"
        return f"{campo['valor']}  (conf: {c_txt}){marca}"

    print("\n=== ENCABEZADO ===")
    print(f"Nombre: {_fmt(encabezado['nombre'])}")
    print(f"Documento: {_fmt(encabezado['documento'])}")
    print(f"Institución: {_fmt(encabezado['institucion'])}")
    print(f"Versión: {_fmt(encabezado['version'])}")

    print("\n=== RESPUESTAS NUMÉRICAS ===")
    for pregunta in range(1, NUMERO_PREGUNTAS_NUMERICAS + 1):
        print(f"Pregunta {pregunta}: {_fmt(numericas[f'pregunta_{pregunta}'])}")

    # ============================================
    # GUARDAR JSON
    # ============================================
    salida = {"encabezado": encabezado, "numericas": numericas}
    os.makedirs(os.path.dirname(RUTA_JSON), exist_ok=True)
    with open(RUTA_JSON, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Resultados guardados en: {RUTA_JSON}")

    # ============================================
    # IMAGEN DE DEBUG
    # ============================================
    generar_debug(debug_items)
    print(f"✅ Debug de recortes guardado en: {RUTA_DEBUG}")

    return salida


def generar_debug(debug_items):
    """Apila verticalmente los recortes enviados a Vision con su texto."""
    ancho_lienzo = 1100
    margen = 15
    cab = 30  # franja de texto sobre cada recorte
    bloques = []

    for titulo, recorte, texto in debug_items:
        if recorte is None or recorte.size == 0:
            continue
        h, w = recorte.shape[:2]
        # Escalar el recorte a un ancho fijo conservando proporción
        ancho_obj = ancho_lienzo - 2 * margen
        escala = ancho_obj / w
        nuevo = cv2.resize(recorte, (ancho_obj, max(1, int(h * escala))))

        bloque = np.full((cab + nuevo.shape[0] + margen, ancho_lienzo, 3), 245, dtype="uint8")
        cv2.putText(bloque, titulo, (margen, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 160), 2)
        bloque[cab:cab + nuevo.shape[0], margen:margen + nuevo.shape[1]] = nuevo
        cv2.rectangle(bloque, (margen, cab),
                      (margen + nuevo.shape[1], cab + nuevo.shape[0]),
                      (150, 150, 150), 1)
        bloques.append(bloque)

    if not bloques:
        return
    lienzo = np.vstack(bloques)
    cv2.imwrite(RUTA_DEBUG, lienzo)


if __name__ == "__main__":
    main()
