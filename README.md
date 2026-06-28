# OCR Service — Calificación Automática de Exámenes Copa STEM

Sistema de calificación automática de hojas de respuestas para las **Olimpiadas de Matemáticas y Lógica — Copa STEM**, organizadas por [Fundación SapienceLab](https://sapiencelab.org) en Copacabana, Antioquia.

Procesa PDFs o imágenes escaneadas de hojas de respuestas, extrae los datos del estudiante y sus respuestas usando OCR (Google Cloud Vision) + visión por computadora (OpenCV), califica contra la clave de la versión del examen (A, B o C) y exporta los resultados a Excel.

---

## Características

- **Entrada flexible**: acepta PDFs multipágina (escáneres, Adobe Scan) o fotos individuales (JPG/PNG), incluso tomadas con cámara sobre una mesa.
- **Preprocesamiento robusto**: detección automática de la hoja, corrección de perspectiva, normalización a tamaño estándar (2480×3309 px) y mejora de contraste.
- **Alineación por anclas**: compensa el desplazamiento de cada hoja respecto a la plantilla calibrada usando la banda oscura del encabezado de la tabla como referencia.
- **Lectura híbrida**:
  - Encabezado (nombre, documento, institución, versión) y preguntas numéricas P1–P4 → **Google Cloud Vision** (una sola llamada por hoja).
  - Selección múltiple P5–P16 → **OpenCV** (conteo de píxeles de tinta por celda).
- **Rescate de hojas difíciles**: reintentos automáticos con realce de contraste, corrección gamma y negativo para hojas quemadas o con exceso de brillo.
- **Fuzzy matching de instituciones**: corrige el nombre de la institución del OCR al oficial más cercano de la base de datos, incluyendo resolución de siglas (ej. "IESLG" → "I.E. San Luis Gonzaga").
- **Validación y revisión**: cada campo se marca con su nivel de confianza; los campos dudosos se resaltan para revisión manual.
- **Exportación a Excel**: libro con fórmulas vivas (VLOOKUP contra la hoja de claves), formato condicional (verde = correcta, amarillo = revisar, rojo = no detectada) y separación automática de nombres/apellidos.

---

## Estructura del proyecto

```
ocr-service/
├── src/
│   ├── calificar_hoja.py        # Pipeline completo de calificación de una hoja
│   ├── procesar_lote.py         # Procesa un PDF/imagen completo (múltiples hojas)
│   ├── procesar_pdf.py          # Convierte PDF/imagen a páginas JPG normalizadas
│   ├── preprocesar_imagen.py    # Perspectiva, tamaño estándar y contraste
│   ├── alinear.py               # Alineación por ancla (offset dx, dy)
│   ├── definir_plantilla.py     # Coordenadas calibradas de la plantilla
│   ├── leer_con_vision.py       # Lectura con Google Cloud Vision (encabezado + numéricas)
│   ├── leer_respuestas.py       # Lectura de selección múltiple con OpenCV
│   ├── datos_instituciones.py   # Lista oficial de instituciones + siglas
│   ├── utils.py                 # Utilidades compartidas (fuzzy match, validación)
│   └── exportar_excel.py        # Genera el Excel con resultados y claves
├── calificar.bat                # Script de ejecución rápida en Windows
├── credentials.json             # Credenciales de Google Cloud (NO incluido en el repo)
├── resultados/                  # Carpeta de salida (generada automáticamente)
└── imagenes_prueba/             # Hojas escaneadas de entrada (no incluidas)
```

---

## Requisitos previos

- **Python 3.10+**
- **Poppler** (para conversión de PDF a imagen) — [descarga para Windows](https://github.com/oschwartz10612/poppler-windows/releases)
- **Cuenta de Google Cloud** con la API de Vision habilitada y un archivo `credentials.json` de service account

### Instalación de dependencias

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install opencv-python numpy pdf2image google-cloud-vision truststore openpyxl
```

> **Nota sobre TLS**: el proyecto usa `truststore` para manejar entornos con interceptación TLS (antivirus/proxy corporativo). El cliente de Vision se crea con transporte REST en lugar de gRPC para aprovechar el almacén de certificados de Windows.

---

## Uso

### Procesar un lote completo (PDF con múltiples hojas)

```bash
python src/procesar_lote.py imagenes_prueba/escaner.pdf B
```

El segundo argumento es la versión del examen (`A`, `B`, `C`, o `AUTO` para detección automática por hoja).

### Procesar una imagen individual

```bash
python src/procesar_lote.py imagenes_prueba/foto_hoja.jpg A
```

### Exportar a Excel

Después de procesar el lote:

```bash
python src/exportar_excel.py
```

Genera `resultados/calificaciones_San_Luis.xlsx` con dos hojas: **Resultados** (una fila por estudiante) y **Respuestas correctas** (claves por versión).

### Calificar una hoja individual (debug)

```bash
python src/calificar_hoja.py resultados/paginas_pdf/pagina_001.jpg
```

---

## Flujo del pipeline

```
PDF / Imagen
    │
    ▼
procesar_pdf.py ──── Rasteriza a 300 DPI + preprocesa cada página
    │
    ▼
preprocesar_imagen.py ──── Detecta hoja → perspectiva → 2480×3309 → contraste
    │
    ▼
alinear.py ──── Detecta banda oscura del encabezado → calcula offset (dx, dy)
    │
    ▼
calificar_hoja.py ──── Orquesta la lectura y calificación:
    │
    ├── leer_con_vision.py ──── 1 llamada a Vision → tokens → encabezado + P1-P4
    │
    ├── leer_respuestas.py ──── OpenCV: conteo de píxeles → P5-P16
    │
    ├── utils.py ──────────── Fuzzy match de institución, validación de documento
    │
    └── Califica contra la clave (A/B/C) → JSON por hoja
    │
    ▼
procesar_lote.py ──── Itera todas las páginas → resumen_lote.json
    │
    ▼
exportar_excel.py ──── JSON → Excel con fórmulas vivas y formato condicional
```

---

## Formato del examen

El examen Copa STEM tiene 16 preguntas con puntaje total de 100:

- **P1–P4** (numéricas, 10 pts c/u): el estudiante escribe un número en la columna (a).
- **P5–P16** (selección múltiple, 5 pts c/u): el estudiante marca con una X la opción (a), (b), (c) o (d).

Existen 3 versiones (A, B, C) con preguntas diferentes. La versión se detecta automáticamente del encabezado de la hoja.

---

## Configuración

### Ruta de Poppler

En `procesar_pdf.py`, ajustar la ruta de Poppler según la instalación local:

```python
POPPLER_PATH = r"C:\poppler-26.02.0\Library\bin"
```

### Credenciales de Google Cloud

Colocar el archivo `credentials.json` en la raíz del proyecto. **Este archivo no se sube al repositorio** (está en `.gitignore`).

### Calibración de la plantilla

Las coordenadas de las celdas están definidas en `definir_plantilla.py`. Para recalibrar con un formato de hoja diferente:

```bash
python src/definir_plantilla.py
```

Esto genera `resultados/plantilla_visualizada.jpg` con los rectángulos dibujados sobre la imagen para verificar la alineación.

---

## Licencia

Uso interno de Fundación SapienceLab.
