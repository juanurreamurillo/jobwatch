# Rúbrica de puntuación 0–100

Puntúa cada vacante contra el CV del usuario. Devuelve un entero 0–100 y una
razón de una frase. Sé consistente entre corridas: aplica siempre estas bandas.

## Bandas

- **85–100 — Encaje fuerte.** El rol coincide con el título/seniority del CV y la
  mayoría de requisitos clave están cubiertos. Modalidad/ubicación compatibles.
- **60–84 — Buen encaje.** Rol relacionado; varios requisitos cubiertos, algunos
  huecos salvables. Vale la pena postular.
- **30–59 — Encaje débil.** Solapamiento parcial (área correcta, seniority o
  stack distinto). Postular solo si el volumen es bajo.
- **0–29 — Encaje pobre.** Rol, seniority o dominio esencialmente distintos.

## Señales (en orden de peso)

1. **Rol y seniority** — ¿el título y el nivel corresponden a la trayectoria del CV?
2. **Requisitos duros** — herramientas, certificaciones, años de experiencia exigidos.
3. **Dominio/industria** — ¿el sector encaja con la experiencia previa?
4. **Modalidad y ubicación** — remoto/híbrido/presencial vs. lo que busca el CV.
5. **Salario** — si la vacante lo declara y está por debajo del mínimo, baja la banda.

## `sin_puntaje`

Si la vacante no trae información suficiente para juzgar el encaje (descripción
vacía o irrelevante al CV), márcala `estado: "sin_puntaje"`, `puntaje: null`, y
explica por qué en la razón. No la descartes: se reporta igual.
