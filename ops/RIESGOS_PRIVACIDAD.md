# Riesgos de privacidad — Rizoma (revisión preliminar, 18/10/2026)

| Riesgo | Situación | Acción |
|---|---|---|
| Búsqueda y feed accesibles sin sesión | En producción hasta el 18/10, `/api/feed` y `/api/feed/search` respondían sin iniciar sesión: la búsqueda permitía listar nombre, rol e institución de cualquier persona. | Corregido y desplegado el 18/10: requieren sesión y se limitan al conjunto. |
| Nombres propios en textos libres | El filtro retira el nombre de la propia persona, pero no nombres de terceros dentro de un CV o una bio. | Advertencia en el aviso; no presentar como anonimización. |
| Proveedor de IA fuera de Argentina | OpenAI trata los textos según sus condiciones; puede conservar registros de seguridad. | `store: false`; acuerdo de tratamiento y garantías pendientes (institucional). |
| Lectura de nombres en puentes y equipos | Resuelto 18/10: docentes y organizaciones ven solo los nombres de su cohorte (institución). | Mantener actualizados los alias de instituciones en `services/cohortes.py`. |
| Copias en el mismo servidor | Las 14 copias diarias están en el mismo servidor y sin cifrar. | Copia externa cifrada (pendiente). |
| Supresión en copias | Una baja tarda hasta 14 días en salir de todos los respaldos. | Declarado en el aviso; reaplicar supresiones antes de restaurar (`PRIVACIDAD.md`). |
| Servicios de terceros en la interfaz | Tipografías alojadas desde el 18/10; las imágenes de algunos proyectos siguen viniendo de Unsplash. | Declarado en el aviso; alojar o quitar esas imágenes. |
| Puerto de la aplicación | uvicorn escucha en `0.0.0.0:6162` y el firewall acepta todo; desde afuera no respondió el 13/10. | Pasar a `--host 127.0.0.1` (nginx ya hace de proxy). |
| Contraseña de la base | Estaba como valor por defecto en `config.py` y quedó en el historial de git. | Quitada del código (18/10); falta cambiar la contraseña del rol `alma` y actualizar `.env`. |
| Responsable del tratamiento | OPEN LAB (UNQ), decidido el 18/10. | Aviso 2026-10-18.2. |
| Nombre completo visible para todo el conjunto | Hasta el 18/10 sugerencias, feed, búsqueda y paneles mostraban el nombre completo. | Desplegado el 18/10 (15:34): inicial y apellido por defecto y controles por persona (`services/visibilidad.py`). |
| Perfil público y mensajes entre conjuntos | `GET /api/users/{id}` devolvía cualquier perfil y se podía escribir a cualquier id. | Desplegado el 18/10 (15:34): 404 fuera del propio conjunto (salvo administración). |
| Nombres en el camino enviado al modelo | «Preguntarle a la red» mandaba al modelo el camino con nombres de personas y usaba toda la base. | Desplegado el 18/10 (15:34): camino sin nombres («quien pregunta → tema → otra persona…»), solo el conjunto. El simulador también quedó acotado al conjunto. |
| CV enviado sin revisión | La copia minimizada iba al modelo sin que la persona la viera; los rangos de años se tomaban como teléfonos. | Desplegado el 18/10 (15:34): vista previa editable antes del envío; rangos de años respetados. Sigue siendo seudonimización. |

## Evaluación de impacto

No hay hoy tratamiento a gran escala de personas reales (unas 10 cuentas fuera de
los conjuntos ficticios). Antes de un piloto con personas reales corresponde una
evaluación de impacto: perfiles de trayectoria + IA + sugerencias entre personas.
