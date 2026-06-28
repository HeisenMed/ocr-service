"""
Utilidades compartidas del pipeline de OCR/calificación.

Centraliza criterios que antes estaban duplicados entre leer_con_vision.py y
calificar_hoja.py:
  - limpiar_texto:    normaliza texto OCR (quita etiqueta impresa, colapsa espacios)
  - comparar_numerica: compara dos números tolerando formato (espacios, . , ceros)
  - documento_valido:  valida formato de documento de identidad colombiano
"""

import re
from difflib import SequenceMatcher

# Validación de documento (Colombia: CC, TI, PPT -> 4 a 12 dígitos)
DOC_MIN_DIGITOS = 4
DOC_MAX_DIGITOS = 12

# Fuzzy matching de institución contra la lista oficial.
#   >= UMBRAL_ALTO   -> se acepta el nombre oficial sin revisión
#   [umbral, ALTO)   -> se sugiere el nombre oficial, pero requiere revisión
#   < umbral         -> se conserva el texto del OCR, requiere revisión
UMBRAL_ALTO_INSTITUCION = 0.80

# Prefijos genéricos que el OCR suele omitir (el alumno escribe solo la parte
# distintiva, p. ej. "San Luis Gonzaga" en vez del nombre completo). Se quitan
# de AMBOS lados antes de comparar para no penalizar esa omisión.
#
# El texto ya viene normalizado (minúsculas, sin acentos, SIN puntos: "I.E." y
# "I. E." quedan como "i e"). Las alternativas largas van primero porque el regex
# toma la PRIMERA que coincide, no la más larga.
_PREFIJO_INSTITUCION_RE = re.compile(
    r"^(?:"
    r"institucion educativa rural|institucion educativa|institucion|"
    r"centro educativo rural|centro educativo|"
    r"instituto|colegio|escuela|"
    r"i e|ie"
    r")\s+"
)

# Longitud mínima (en caracteres) del texto OCR para intentar el "ratio parcial"
# (comparar contra la mejor ventana del nombre oficial). Evita que textos muy
# cortos (2-3 letras) hagan match parcial espurio contra cualquier institución.
_MIN_LEN_PARCIAL = 5


# Palabras de las etiquetas impresas del formulario. Si Vision NO captó el ':'
# (a veces ocurre), las quitamos por nombre para no dejarlas pegadas al valor
# manuscrito. Se comparan sin acentos ni mayúsculas.
_ETIQUETAS_ENCABEZADO = {
    "nombre", "completo", "numero", "número", "de", "identidad",
    "institucion", "institución", "educativa", "version", "versión", "firma",
}


def _sin_acentos(s):
    # Incluye ñ->n y ü->u para que el matching de instituciones sea insensible
    # a tildes y eñes (los estudiantes rara vez las escriben a mano).
    tabla = str.maketrans("áéíóúÁÉÍÓÚñÑüÜ", "aeiouAEIOUnNuU")
    return s.translate(tabla)


def limpiar_texto(texto):
    """Normaliza texto OCR del encabezado.

    Las etiquetas impresas del formulario ("Nombre completo:", "Institución
    educativa:") terminan en ':' y la escritura a mano no contiene ':', así que
    nos quedamos con lo que va después del último ':'. Si Vision no detectó el
    ':', quitamos por nombre las palabras de la etiqueta que hayan quedado al
    principio (robustez ante OCR que omite el ':'). Además colapsa espacios.
    """
    if not texto:
        return ""
    if ":" in texto:
        texto = texto.rsplit(":", 1)[1]
    palabras = texto.split()
    # Descartar las palabras-etiqueta SOLO mientras aparezcan al inicio; en
    # cuanto empieza el valor real (una palabra que no es etiqueta) paramos,
    # para no borrar partes legítimas del nombre.
    while palabras and _sin_acentos(palabras[0]).lower().strip(".,") in _ETIQUETAS_ENCABEZADO:
        palabras.pop(0)
    return " ".join(palabras)


def normalizar_numero(texto):
    """Quita espacios y separadores (. ,) de un número."""
    return re.sub(r"[\s.,]", "", texto)


def comparar_numerica(detectada, correcta):
    """Compara dos respuestas numéricas tras normalizarlas.

    Quita espacios/puntos/comas y compara como enteros (ignora ceros a la
    izquierda). Si alguna no es convertible a int, compara como string limpio
    sin ceros a la izquierda.
    """
    if detectada in ("", "no detectado"):
        return False
    d = normalizar_numero(detectada)
    c = normalizar_numero(correcta)
    try:
        return int(d) == int(c)
    except ValueError:
        return d.lstrip("0") == c.lstrip("0")


def documento_valido(valor, min_digitos=DOC_MIN_DIGITOS, max_digitos=DOC_MAX_DIGITOS):
    """True si el documento es solo dígitos y tiene entre 4 y 12 caracteres."""
    return valor.isdigit() and min_digitos <= len(valor) <= max_digitos


def _normalizar_para_match(texto):
    """Normaliza para comparar: minúsculas, sin acentos/eñes, sin puntuación.

    Los puntos se vuelven espacios ("I.E." -> "i e") y el resto de signos se
    descarta, dejando solo letras/dígitos/espacios con espacios colapsados.
    """
    s = _sin_acentos(texto).lower().replace(".", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _quitar_prefijo_generico(texto):
    """Quita el prefijo institucional genérico ('I.E.', 'Colegio', etc.).

    Recibe texto YA normalizado por _normalizar_para_match. Si tras quitarlo no
    queda nada (el OCR solo leyó el prefijo), devuelve el texto sin tocar.
    """
    resto = _PREFIJO_INSTITUCION_RE.sub("", texto, count=1).strip()
    return resto if resto else texto


def _clave_sigla(texto):
    """Limpia el texto a una sigla canónica: solo alfanuméricos, en MAYÚSCULAS."""
    return re.sub(r"[^a-z0-9]", "", _sin_acentos(texto).lower()).upper()


def _ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()


def _ratio_parcial(a, b):
    """Similitud del texto corto contra la MEJOR ventana del largo (partial ratio).

    Permite que un fragmento ("Normal Superior", "Emiliano") matchee un nombre
    oficial largo del que es subcadena. Se omite si el texto corto es muy breve
    (< _MIN_LEN_PARCIAL) para no generar coincidencias espurias.
    """
    corto, largo = (a, b) if len(a) <= len(b) else (b, a)
    m = len(corto)
    if m < _MIN_LEN_PARCIAL or not largo:
        return 0.0
    mejor = 0.0
    for i in range(len(largo) - m + 1):
        r = _ratio(corto, largo[i:i + m])
        if r > mejor:
            mejor = r
            if mejor == 1.0:
                break
    return mejor


def match_institucion(texto_ocr, lista_instituciones, umbral=0.6, siglas=None):
    """Corrige el nombre de institución del OCR al oficial más parecido.

    Flujo:
      texto OCR -> limpiar -> ¿sigla conocida? -> sí -> nombre oficial (conf 1.0)
                                                -> no -> fuzzy match contra lista

    1) SIGLAS: se limpia el texto (sin espacios/puntos, mayúsculas) y se busca una
       coincidencia EXACTA en `siglas` (por defecto SIGLAS_INSTITUCIONES). Si la
       hay, se devuelve el nombre oficial con similitud 1.0 y sin revisión.
    2) FUZZY: SequenceMatcher insensible a mayúsculas, acentos y eñes. Como el OCR
       suele omitir el prefijo genérico ("I.E. ...") y a veces solo escribe un
       fragmento, se toma el MEJOR de tres medidas: nombre completo, parte
       distintiva (sin prefijo) y ratio parcial (subcadena) de esa parte.

    Devuelve un dict:
      - valor:              nombre oficial si hay match >= umbral; si no, el OCR.
      - institucion_match:  mejor candidato oficial (aunque quede bajo el umbral).
      - similitud:          puntaje [0..1] del mejor candidato (redondeado).
      - requiere_revision:  False solo si similitud >= UMBRAL_ALTO_INSTITUCION.
      - metodo:             "sigla" | "fuzzy" | "ninguno".

    Umbrales:
      >= 0.80  -> nombre oficial, requiere_revision=False
      [umbral, 0.80) -> nombre oficial sugerido, requiere_revision=True
      < umbral -> texto original del OCR, requiere_revision=True
    """
    original = (texto_ocr or "").strip()
    if not original or original == "no detectado" or not lista_instituciones:
        return {"valor": original, "institucion_match": None,
                "similitud": 0.0, "requiere_revision": True, "metodo": "ninguno"}

    # 1) Siglas (match exacto tras limpiar). Lazy import para no acoplar utils a
    #    datos_instituciones; el llamador puede pasar su propio dict.
    if siglas is None:
        try:
            from datos_instituciones import SIGLAS_INSTITUCIONES as siglas
        except Exception:
            siglas = {}
    if siglas:
        siglas_norm = {_clave_sigla(k): v for k, v in siglas.items()}
        oficial = siglas_norm.get(_clave_sigla(original))
        if oficial:
            return {"valor": oficial, "institucion_match": oficial,
                    "similitud": 1.0, "requiere_revision": False, "metodo": "sigla"}

    # 2) Fuzzy matching contra la lista completa.
    ocr_norm = _normalizar_para_match(original)
    ocr_core = _quitar_prefijo_generico(ocr_norm)

    mejor_nombre = None
    mejor_score = 0.0
    for nombre in lista_instituciones:
        oficial_norm = _normalizar_para_match(nombre)
        oficial_core = _quitar_prefijo_generico(oficial_norm)
        score = max(
            _ratio(ocr_norm, oficial_norm),       # nombre completo
            _ratio(ocr_core, oficial_core),        # parte distintiva
            _ratio_parcial(ocr_core, oficial_core),  # fragmento/subcadena
        )
        if score > mejor_score:
            mejor_score = score
            mejor_nombre = nombre

    similitud = round(mejor_score, 4)
    if mejor_score >= UMBRAL_ALTO_INSTITUCION:
        return {"valor": mejor_nombre, "institucion_match": mejor_nombre,
                "similitud": similitud, "requiere_revision": False, "metodo": "fuzzy"}
    if mejor_score >= umbral:
        return {"valor": mejor_nombre, "institucion_match": mejor_nombre,
                "similitud": similitud, "requiere_revision": True, "metodo": "fuzzy"}
    return {"valor": original, "institucion_match": mejor_nombre,
            "similitud": similitud, "requiere_revision": True, "metodo": "fuzzy"}
