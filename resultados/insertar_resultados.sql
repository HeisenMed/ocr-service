
-- Resultados físicos - San Luis Gonzaga - Procesados por OCR
-- REVISAR nombres y documentos antes de ejecutar
-- Institución normalizada al nombre oficial de Supabase por fuzzy match + siglas (similitud >= 0.80)

-- Página 1 (versión B) - revisar: Documento, P4, P13
INSERT INTO resultados_prueba_copa_stem (
  numero_documento, respuestas, puntaje_obtenido, puntaje_total, porcentaje,
  publicado, created_at, nombres, apellidos, institucion_educativa, grado_escolar,
  sesion_id, tiempo_usado_segundos, cambios_pestana, intentos_copiar, intentos_pegar,
  intentos_click_derecho, eventos_sospechosos
) VALUES (
  '5052540',
  '{"pregunta_1":"4","pregunta_2":"9","pregunta_3":"5000","pregunta_4":"128","pregunta_5":"d","pregunta_6":"a","pregunta_7":"a","pregunta_8":"d","pregunta_9":"a","pregunta_10":"d","pregunta_11":"a","pregunta_12":"c","pregunta_13":"a","pregunta_14":"c","pregunta_15":"b","pregunta_16":"d"}'::jsonb,
  10, 100, 10,
  false, now(), 'Mathias Alejandro Lopez Moret', NULL, 'I.E. San Luis Gonzaga', 9,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL
);

-- Página 2 (versión C) - revisar: Nombre, Documento, P1, P2, P9, P11
INSERT INTO resultados_prueba_copa_stem (
  numero_documento, respuestas, puntaje_obtenido, puntaje_total, porcentaje,
  publicado, created_at, nombres, apellidos, institucion_educativa, grado_escolar,
  sesion_id, tiempo_usado_segundos, cambios_pestana, intentos_copiar, intentos_pegar,
  intentos_click_derecho, eventos_sospechosos
) VALUES (
  NULL,
  '{"pregunta_1":"no detectado","pregunta_2":"10","pregunta_3":"12","pregunta_4":"8","pregunta_5":"b","pregunta_6":"c","pregunta_7":"c","pregunta_8":"b","pregunta_9":"a","pregunta_10":"d","pregunta_11":"b","pregunta_12":"d","pregunta_13":"d","pregunta_14":"c","pregunta_15":"b","pregunta_16":"a"}'::jsonb,
  15, 100, 15,
  false, now(), 'Gabriel Buzman vazques', NULL, 'I.E. San Luis Gonzaga', NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL
);

-- Página 3 (versión B) - revisar: Documento, P4
INSERT INTO resultados_prueba_copa_stem (
  numero_documento, respuestas, puntaje_obtenido, puntaje_total, porcentaje,
  publicado, created_at, nombres, apellidos, institucion_educativa, grado_escolar,
  sesion_id, tiempo_usado_segundos, cambios_pestana, intentos_copiar, intentos_pegar,
  intentos_click_derecho, eventos_sospechosos
) VALUES (
  '1056779347',
  '{"pregunta_1":"1","pregunta_2":"10","pregunta_3":"12","pregunta_4":"800","pregunta_5":"b","pregunta_6":"c","pregunta_7":"c","pregunta_8":"b","pregunta_9":"a","pregunta_10":"d","pregunta_11":"b","pregunta_12":"a","pregunta_13":"d","pregunta_14":"c","pregunta_15":"b","pregunta_16":"a"}'::jsonb,
  10, 100, 10,
  false, now(), 'Emmanuel lliguita Muñoz Muñoz', NULL, 'I.E. San Luis Gonzaga', 9,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL
);

-- Página 4 (versión C) - revisar: Nombre, P1, P2, P3, P4, P14
INSERT INTO resultados_prueba_copa_stem (
  numero_documento, respuestas, puntaje_obtenido, puntaje_total, porcentaje,
  publicado, created_at, nombres, apellidos, institucion_educativa, grado_escolar,
  sesion_id, tiempo_usado_segundos, cambios_pestana, intentos_copiar, intentos_pegar,
  intentos_click_derecho, eventos_sospechosos
) VALUES (
  '1035430981',
  '{"pregunta_1":"no detectado","pregunta_2":"no detectado","pregunta_3":"no detectado","pregunta_4":"no detectado","pregunta_5":"a","pregunta_6":"c","pregunta_7":"b","pregunta_8":"b","pregunta_9":"a","pregunta_10":"c","pregunta_11":"d","pregunta_12":"a","pregunta_13":"b","pregunta_14":"sin responder","pregunta_15":"a","pregunta_16":"d"}'::jsonb,
  15, 100, 15,
  false, now(), 'Emmanuel Londoño echavarria', NULL, 'I.E. San Luis Gonzaga', NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL
);

-- Página 5 (versión A) - revisar: Nombre, P7, P9, P11, P12, P14, P15, P16
INSERT INTO resultados_prueba_copa_stem (
  numero_documento, respuestas, puntaje_obtenido, puntaje_total, porcentaje,
  publicado, created_at, nombres, apellidos, institucion_educativa, grado_escolar,
  sesion_id, tiempo_usado_segundos, cambios_pestana, intentos_copiar, intentos_pegar,
  intentos_click_derecho, eventos_sospechosos
) VALUES (
  '1077857926',
  '{"pregunta_1":"40","pregunta_2":"3","pregunta_3":"108","pregunta_4":"20","pregunta_5":"a","pregunta_6":"b","pregunta_7":"c","pregunta_8":"c","pregunta_9":"a","pregunta_10":"b","pregunta_11":"b","pregunta_12":"c","pregunta_13":"c","pregunta_14":"a","pregunta_15":"a","pregunta_16":"d"}'::jsonb,
  85, 100, 85,
  false, now(), 'Jhossep David Trujille Clatos', NULL, 'I.E. San Luis Gonzaga', NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL
);
