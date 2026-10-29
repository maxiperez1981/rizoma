# Operación de privacidad — Rizoma (18/10/2026)

Basado en lo que ya funciona en Desarrollo2 (`/home/desarrollo2/ops/`), adaptado a Rizoma.

## Alcance

Rizoma trata datos de cuentas (correo, nombre, rol, institución), perfiles
(bio, temas, resumen, embedding), extractos de CV ya minimizados, vínculos
(sugerencias, explicaciones, notificaciones, mensajes, conexiones, resultados)
y registros técnicos. El detalle está en `REGISTRO_TRATAMIENTOS.md`.

## Aviso y constancia de lectura

- Texto: `static/privacidad.html`, servido en `/privacidad`.
- Versión: `NOTICE_VERSION` en `services/privacy_notice.py` y
  `AVISO_PRIVACIDAD_VERSION` en `static/js/app.js` (un test exige que coincidan
  con la que figura en la página).
- Al arrancar se publica la versión en `privacy_notices` con su huella y una
  copia del texto. **Si se edita el aviso sin subir la versión, la aplicación no
  arranca.** Para cambiar el texto: subir la versión en los tres lugares.
- La constancia (`privacy_acknowledgments`) se pide al registrarse y, a quien
  ya tiene cuenta, al ingresar. Sin la versión vigente leída, estas funciones
  responden 428: carga de CV o texto, edición del perfil, explicación de una
  sugerencia y preguntas a la red. La constancia no es consentimiento para
  difusión ni para investigación.

## Minimización ante la IA

`services/privacy_service.py` retira correos, enlaces, documentos, teléfonos,
direcciones y cuentas, y además el nombre y el correo de la propia persona
(`identificadores_de_usuario`). Se aplica a la copia del CV que va al modelo, al
extracto que se guarda, al texto del embedding y a los perfiles que se comparan
(con etiquetas «Persona A/B»). No detecta nombres de terceros en texto libre ni
garantiza anonimato: decir «minimizado» o «seudonimizado», no «anonimizado».

Llamadas a OpenAI con `store: false` explícito. No activa retención cero ni
elimina los registros de seguridad del proveedor. Los errores del proveedor se
registran solo por tipo (sin su texto, que puede traer partes del pedido).

## Pedidos de derechos

- La persona los deja en «Datos base» → «Mis datos y privacidad»
  (`privacy_requests`), o por correo al referente del aviso.
- Copia: `scripts/privacidad_exportar.py --email ... [--solicitud id]` deja un
  JSON 600 en `/var/lib/rizoma-privacy/exportaciones/`. **Revisarlo antes de
  enviarlo**: incluye datos de terceros (mensajes recibidos, sugerencias).
- Baja: `scripts/privacidad_suprimir.py --email ...` muestra el plan y su
  huella; con `--confirmar <huella> --operador <nombre>` borra, si hay una copia
  de respaldo de menos de 26 h. Los proyectos creados por la persona se
  desvinculan, no se borran. Queda en `privacy_purge_audit` sin datos personales.
- Rectificación: la persona corrige su perfil; lo demás, a mano y registrado en
  `privacy_requests.resolucion`.
- Plazo orientativo de respuesta: diez días hábiles (Ley 25.326, art. 14 para el
  acceso). Confirmar con la institución.

## Conservación

Plazos propuestos en `services/privacy_retention.py` (pendientes de decisión
institucional): sugerencias y explicaciones 12 meses; notificaciones leídas 6
meses y no leídas 12; extractos de CV 12 meses salvo el último de cada persona.
Excluye el conjunto de prueba de la ponencia (`demo.unq.*`, ficticio).

- Revisión diaria, solo informa: `systemd/rizoma-privacy-review.timer`
  (`scripts/privacidad_revision.py`). Ver con `journalctl -u rizoma-privacy-review`.
- Aplicar: `scripts/privacidad_revision.py --aplicar <huella> --operador <nombre>`,
  con respaldo de menos de 26 h. Queda en `privacy_purge_audit`.

## Copias y restauración

`backup_db.sh` (timer diario) guarda 14 copias en `backups/db/`, en el mismo
servidor. Una supresión llega a todas las copias recién al rotar (14 días).
**Antes de restaurar una copia, reaplicar las supresiones** registradas en
`privacy_purge_audit` posteriores a esa copia. Copia externa cifrada: pendiente.

## Navegador

Al salir (y al ingresar con otra cuenta) se borran del almacenamiento local el
token y los datos de la persona (`aa_token`, `rizoma_*`). Las respuestas de
`/api/` y `/auth/` llevan `Cache-Control: no-store, private`.

## Responsable

OPEN LAB, de la Universidad Nacional de Quilmes (decisión del 18/10/2026; aviso
2026-10-18.2). Referente operativo: Maximiliano Ariel Pérez, director de OPEN LAB.

## Nombres en puentes y equipos (cohortes)

`services/cohortes.py`: la cohorte es la institución declarada, normalizada (la
parte antes de «·», sin tildes ni mayúsculas, con alias «Universidad Nacional de
Quilmes» → «unq»). Administración ve todos los nombres; docentes y
organizaciones, solo los de su cohorte; el resto, «Persona N». Los equipos se
arman dentro del conjunto de quien consulta. Si aparecen variantes nuevas de una
misma institución, sumarlas a `ALIAS`.

## Tipografías

Alojadas en `static/fonts/` desde el 18/10 (Montserrat y Source Sans 3, SIL OFL
1.1; origen y licencias en `static/fonts/LEEME.md`). La interfaz ya no carga
nada de Google Fonts. Las imágenes de algunos proyectos siguen viniendo de Unsplash.

## Validaciones institucionales pendientes

- Acuerdo de tratamiento de datos con OpenAI y garantías de transferencia internacional.
- Aprobar los plazos de conservación.
- Copia de respaldo externa y cifrada.
- Cambiar la contraseña del rol `alma` de la base (quedó en el historial de git).

## Qué ven los demás de cada persona (visibilidad)

`services/visibilidad.py`, columna `users.visibilidad` (JSON; vacío = valores
por defecto; migración `sql/2026_10_18b_visibilidad.sql`). Cada persona elige en
«Mis datos y privacidad» → «Qué ven los demás de mí»:

- nombre: inicial y apellido por defecto («M. Iglesias»), o completo;
- bio y resumen: las personas de su conjunto (por defecto) o nadie;
- aparecer en sugerencias de otras personas (si no, como puente se muestra
  «Persona de la red»), en la búsqueda, y mostrar la institución (todo sí por defecto).

La propia persona y la administración ven siempre todo; las organizaciones se
muestran con su nombre. Se aplica en sugerencias, explicación, perfil público
(404 fuera del conjunto), feed, búsqueda (sobre lo visible), mensajes,
notificaciones, grafo, caminos, red completa, equipos, puentes, simulador y
«Preguntarle a la red». Excepción declarada: en una postulación a un proyecto,
quien la revisa ve nombre completo y correo (para certificar). Los mensajes
solo se envían dentro del propio conjunto.

## Vista previa del CV (seudonimización)

`POST /api/copilot/vista-previa` lee el archivo o el texto, aplica la misma
minimización (`privacy_service.minimizar_con_detalle`, que conserva renglones y
cuenta lo retirado) y devuelve la copia. No llama a ningún modelo ni guarda nada.
La persona la revisa y corrige en el cuadro del CV; recién al confirmar se envía
a `POST /api/copilot` (con el tipo de archivo, no su nombre), que vuelve a
minimizar. Los rangos de años («2015 - 2018») ya no se toman como teléfonos.
