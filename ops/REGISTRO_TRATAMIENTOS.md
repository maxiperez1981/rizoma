# Inventario de tratamientos y destinatarios — Rizoma

Actualizar este archivo con cada función nueva que guarde o envíe datos personales.

## Tratamientos

| Tratamiento | Datos | Dónde | Quién accede | Conservación |
|---|---|---|---|---|
| Cuenta | correo, nombre, rol, institución, hash de contraseña | `users` | la persona; administración técnica | mientras exista la cuenta |
| Perfil y grafo | bio, aportes, aprendizajes, intereses, resumen IA, temas, embedding | `users`, `user_topics`, `topics` | personas del mismo conjunto según lo que cada una elige mostrar (nombre abreviado o completo, rol, institución, temas, resumen o bio) | mientras exista la cuenta |
| Preferencias de visibilidad | nombre, bio, sugerencias, búsqueda, institución | `users.visibilidad` | la persona; administración | mientras exista la cuenta |
| Carga de CV o texto | texto del CV (no se guarda; la persona revisa la copia seudonimizada antes de enviarla); extracto minimizado ≤1.000 caracteres; tipo de archivo | `rizoma_snapshots` | la persona | último: mientras exista la cuenta; anteriores: 12 meses |
| Sugerencias | pares de personas, similitud, explicación del modelo (con veredicto y puntaje que no se muestran) | `match_candidates`, `ai_match_suggestions` | las dos personas del par (la explicación, quien la pide) | 12 meses |
| Notificaciones | aviso de un vínculo nuevo, con el nombre de la otra persona | `notifications` | destinatario | leídas 6 meses; no leídas 12 |
| Mensajes, conexiones, publicaciones, postulaciones, credenciales | contenido y metadatos | tablas homónimas | emisor y receptor; publicaciones: el conjunto | mientras exista la cuenta |
| Resultados de sugerencias | «En curso», «Sirvió», «Colaboró» | `match_outcomes` | la persona; análisis agregado | mientras exista la cuenta |
| Lecturas de la red (actividades, demanda, puentes) | agregados; nombres de puentes y equipos: administración todos, docentes y organizaciones solo su cohorte (institución) | `emerging_activities`, `network_insights` | según rol | hasta la próxima corrida |
| Evaluación a ciegas | pares anonimizados y calificaciones | `blind_pairs`, `blind_ratings` | administración | mientras exista la cuenta |
| Constancia del aviso | versión y fecha por cuenta | `privacy_acknowledgments` | administración | mientras exista la cuenta |
| Pedidos de derechos | tipo, detalle, estado, seudónimo | `privacy_requests` | administración | registro permanente (sin datos personales tras una baja) |
| Auditoría de supresiones y depuraciones | seudónimo, cantidades, huella, respaldo usado | `privacy_purge_audit` | administración | permanente |
| Registros técnicos | logs del servicio y de nginx | journald, `/var/log/nginx` | administración técnica | hasta 3 meses (journald del servidor) |
| Copias de respaldo | base completa | `backups/db/` (mismo servidor) | administración técnica | 14 copias diarias |

## Destinatarios y proveedores a formalizar

| Proveedor | Para qué | Qué recibe | Estado |
|---|---|---|---|
| OpenAI (chat completions) | armar el perfil desde el CV, coincidencias con proyectos, explicaciones de sugerencias, nombres de actividades, unificación de temas, preguntas a la red | texto minimizado (sin correos, teléfonos, documentos, enlaces, nombre ni correo propios); perfiles con etiquetas | `store: false`; acuerdo de tratamiento pendiente |
| OpenAI (embeddings) | afinidad entre perfiles y unificación de temas | texto del perfil minimizado; etiquetas de temas | acuerdo pendiente |
| Anthropic (respaldo, hoy sin clave configurada) | mismas funciones si se activa | mismo texto minimizado | sin uso |
| Google Fonts | (ya no se usa) | — | resuelto 18/10: tipografías alojadas en `static/fonts/` |
| Unsplash | imágenes de algunos proyectos | dirección IP del navegador | pendiente alojarlas en el servidor |

## Inventario técnico reproducible

Tablas con datos de personas (columnas que las identifican): ver `SUJETO` en
`services/privacy_export.py`. La exportación y la supresión usan esa lista.

## Cambios

- 18/10/2026 (tarde): visibilidad por persona (nombre abreviado por defecto,
  bio, sugerencias, búsqueda, institución), vista previa editable del CV, perfil
  público y mensajes acotados al conjunto, caminos sin nombres hacia el modelo en
  «Preguntarle a la red».
- 18/10/2026: aviso versionado, constancia, minimización con identificadores
  propios, pedidos de derechos, exportación y supresión con plan, conservación con
  revisión diaria, feed y búsqueda con sesión y por conjunto, limpieza del
  navegador al salir, `no-store` en la API, `store: false`, logs sin contenido.
