# Incidentes de datos — Rizoma

Canal: el correo del aviso de privacidad, asunto «Incidente de privacidad — Rizoma».

## Qué hacer

1. **Contener.** Cortar el acceso indebido (revocar la clave expuesta, rotar
   `SECRET_KEY` para invalidar tokens, apagar la función afectada o el servicio).
   No borrar evidencia.
2. **Registrar** (expediente, sin copiar datos personales innecesarios): fecha y
   hora de detección, quién avisó, qué datos y cuántas personas, cómo ocurrió,
   desde cuándo, qué se hizo y cuándo.
3. **Evaluar** el riesgo para las personas: qué datos (perfil, CV, mensajes),
   si eran de personas reales o de conjuntos ficticios, si pudieron copiarse.
4. **Decidir la comunicación** con la institución responsable: a las personas
   afectadas y, si corresponde, a la Agencia de Acceso a la Información Pública.
5. **Recuperar y cerrar.** Corregir la causa y probar con datos sintéticos.
   Si hay que restaurar una copia, reaplicar antes las supresiones registradas
   en `privacy_purge_audit` posteriores a la copia. Documentar lecciones.

## Comandos útiles

- Invalidar todas las sesiones: cambiar `SECRET_KEY` en `.env` y reiniciar
  `rizoma.service` (todos deben volver a ingresar).
- Quién leyó qué versión del aviso: tabla `privacy_acknowledgments`.
- Pedidos abiertos: `scripts/privacidad_revision.py` (solo informa).

## Plantilla de expediente

Fecha de detección · Quién informó · Descripción · Datos y personas afectadas ·
Causa · Contención (qué y cuándo) · Evaluación de riesgo · Comunicación decidida ·
Corrección · Verificación · Lecciones · Cierre.
