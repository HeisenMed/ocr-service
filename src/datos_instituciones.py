"""
Lista oficial de instituciones educativas para el fuzzy matching del encabezado.

El OCR rara vez lee el nombre institucional exactamente como está registrado en
la base de datos (acentos, mayúsculas, ruido, abreviaturas). match_institucion()
en utils.py compara el texto detectado contra esta lista y lo corrige al nombre
oficial.

Fuente: tabla `instituciones_educativas` de Supabase (municipios de Bello,
Copacabana y Girardota). Mantener sincronizada cuando cambie en Supabase.
"""

INSTITUCIONES = [
    # Bello
    "Colegio Bethlemitas",
    "Colegio El Rosario",
    "Colegio La Salle",
    "Colegio Mano Amiga",
    "I.E. Abraham Reyes",
    "I.E. Alberto Lebrún Múnera",
    "I.E. Andrés Bello",
    "I.E. Atanasio Girardot",
    "I.E. Barrio París",
    "I.E. Betsabé Espinal",
    "I.E. Carlos Pérez Mejía",
    "I.E. Cincuentenario de Fabricato",
    "I.E. Comercial Antonio Roldán Betancur",
    "I.E. Concejo de Bello",
    "I.E. Divina Eucaristía",
    "I.E. Federico Sierra Arango",
    "I.E. Fernando Vélez",
    "I.E. Fontidueño Jaime Arango Rojas",
    "I.E. Gilberto Echeverri Mejía",
    "I.E. Hernán Villa Baena",
    "I.E. Jorge Eliécer Gaitán",
    "I.E. Josefa Campos",
    "I.E. La Camila",
    "I.E. La Milagrosa",
    "I.E. La Navarra",
    "I.E. La Primavera",
    "I.E. Marco Fidel Suárez",
    "I.E. Nueva Generación",
    "I.E. Playa Rica",
    "I.E. Raquel Jaramillo",
    "I.E. Sagrado Corazón",
    "I.E. Santa Catalina",
    "I.E. Tomás Cadavid Restrepo",
    "I.E. Villa del Sol",
    # Copacabana
    "Colegio Cooperativo Juan del Corral",
    "Colegio Fundación Servicio Juvenil Bosconia Horizontes",
    "Colegio La Asunción",
    "Colegio Paisitas Juguetones",
    "Colegio Paso a Paso",
    "Colegio San Rafael",
    "Colegio Santa Leoní Aviat",
    "Colegio Unitecnicas",
    "I. E. Presbítero Bernardo Montoya Giraldo",
    "I.E. Escuela Normal Superior María Auxiliadora",
    "I.E. Gabriela Mistral",
    "I.E. José Miguel de Restrepo y Puerta",
    "I.E. San Juan de la Tasajera",
    "I.E. San Luis Gonzaga",
    # Girardota
    "Colegio Cenforma",
    "Colegio Ferrini (Sede Girardota)",
    "Colegio Forjadores del Mañana",
    "Colegio Juan Bernardone",
    "Colegio Neosistemas",
    "Colegio Nuestra Señora del Rosario",
    "Colegio The Farm Country School",
    "I.E. Atanasio Girardot",
    "I.E. Emiliano García",
    "I.E. Manuel José Sierra",
    "I.E. San Andrés",
    "Instituto Parroquial Nuestra Señora de la Presentación",
]

# Siglas que los estudiantes escriben por pereza en vez del nombre completo.
# match_institucion() las resuelve por coincidencia EXACTA (tras limpiar el texto:
# quitar espacios/puntos y pasar a mayúsculas) ANTES del fuzzy matching, así
# "I.E.S.L.G" / "ieslg" -> "IESLG" -> "I.E. San Luis Gonzaga" con confianza 1.0.
SIGLAS_INSTITUCIONES = {
    "IESLG": "I.E. San Luis Gonzaga",
    "IENSMMA": "I.E. Escuela Normal Superior María Auxiliadora",
    "IENORMA": "I.E. Escuela Normal Superior María Auxiliadora",
    "IENORMAL": "I.E. Escuela Normal Superior María Auxiliadora",
    "NORMAL": "I.E. Escuela Normal Superior María Auxiliadora",
    "IEEG": "I.E. Emiliano García",
    "IEMFS": "I.E. Marco Fidel Suárez",
    "IEJMRP": "I.E. José Miguel de Restrepo y Puerta",
    "IEPBMG": "I. E. Presbítero Bernardo Montoya Giraldo",
    "IEGM": "I.E. Gabriela Mistral",
    "IESJT": "I.E. San Juan de la Tasajera",
    "IEMJS": "I.E. Manuel José Sierra",
    "IESA": "I.E. San Andrés",
    "IEAG": "I.E. Atanasio Girardot",
    "SLG": "I.E. San Luis Gonzaga",
    "SLGONZAGA": "I.E. San Luis Gonzaga",
}
