# jobwatch

**Un agregador de empleos para la consola.** Corre una búsqueda en varios portales a la vez, deduplica los resultados, los puntúa contra tu propio CV y te entrega un reporte de solo lo que es *nuevo* desde la última corrida — sin abrir cinco pestañas.

> Estado: **0.1.0 Beta en producción.** MVP + Plan A (multi-portal engine) + Plan B (CLI + skill de Claude Code) completados. Hoja de ruta de próximas fases en [`docs/design.md`](docs/design.md). Se aceptan contribuciones.

---

## Por qué

Cada portal de empleo tiene su propia interfaz, su propia búsqueda y su propio ruido. `jobwatch` los trata como fuentes de datos detrás de un único contrato, para que revises una sola lista consolidada y ordenada a tu manera — en la terminal o desde una corrida programada.

Lee únicamente lo que una búsqueda pública ya te muestra, a volumen personal y bajo, con pausas entre peticiones. Ver [Uso responsable](#uso-responsable).

## Cómo funciona

```
[Conectores]              [Matcher híbrido]        [Store + Reporte]
 uno por portal    ──►     filtro local barato ──►   SQLite + Markdown
 cada uno emite            luego puntuación LLM       dedup de dos niveles
 Vacante normalizada       de las sobrevivientes      reporte de solo nuevas
```

Cada conector implementa el mismo contrato — `buscar(criterios) -> ResultadoConector` — así que agregar un portal es un archivo nuevo, no una reescritura. El diseño completo y las decisiones detrás de cada elección están en [`docs/design.md`](docs/design.md).

### Puntos clave del diseño

- **Contrato único de conector.** Los portales son intercambiables detrás de un modelo Pydantic `Vacante`. La normalización (textos de salario, nombres de ciudad, modalidad) vive dentro de cada conector.
- **Fail-loud.** Un conector que devuelve cero resultados distingue *"búsqueda vacía"* de *"roto / bloqueado"*, para que una fuente que falla en silencio nunca se haga pasar por "no hay nada nuevo".
- **Dedup de dos niveles.** Coincidencia exacta por el id nativo del portal, más un fingerprint de contenido que colapsa la misma oferta vista en varios portales o re-publicada con id nuevo.
- **Match híbrido.** Un filtro local, gratis y determinista, descarta ~80% del ruido; solo las sobrevivientes las puntúa un LLM contra tu CV. Las cartas de presentación se redactan de forma perezosa, bajo demanda — no para cada oferta.

## Hoja de ruta

- [ ] **Fase 0 — descubrimiento de endpoints.** Mapear los endpoints reales y la forma de respuesta de cada portal en `docs/endpoints.md` (un entregable en sí mismo). Herramientas: DevTools del navegador (exportar HAR), [`mitmproxy2swagger`](https://github.com/alufers/mitmproxy2swagger), [`jsluice`](https://github.com/BishopFox/jsluice), [`curlconverter`](https://github.com/curlconverter/curlconverter).
- [ ] Conectores: Computrabajo, elempleo, Magneto, Indeed (vía [JobSpy](https://github.com/speedyapply/JobSpy)).
- [ ] Matcher híbrido + store SQLite + reporte Markdown.
- [ ] Receta de programación (cron / Programador de Tareas).
- [ ] Soporte opcional de sesión para portales que lo requieran (diseñado, construido solo cuando haga falta).

## Tecnología

Python · [`curl_cffi`](https://github.com/lexiforest/curl_cffi) · [`extruct`](https://github.com/scrapinghub/extruct) · [`pydantic`](https://github.com/pydantic/pydantic) · [`python-jobspy`](https://github.com/speedyapply/JobSpy)

## Instalación

```bash
pipx install jobwatch          # cuando esté publicado en PyPI
# o desde el repo:
pipx install git+https://github.com/juanurreamurillo/jobwatch
```

### Como skill de Claude Code

Instala el paquete (arriba) y la skill del directorio `skill/`. En tu sesión,
`/jobwatch` cosecha, puntúa contra tu CV y reporta — sin API key. Ver
[`skill/SKILL.md`](skill/SKILL.md).

## Uso local

Instala el proyecto y sus dependencias en un entorno virtual, y provee tu CV como texto plano en `data/cv.txt` (esta carpeta está en `.gitignore` — nunca se sube):

```bash
python -m venv .venv
.venv/bin/pip install -e .
mkdir -p data && cp /ruta/a/tu-cv.txt data/cv.txt
```

Corre una búsqueda (necesita `ANTHROPIC_API_KEY` para la puntuación):

```bash
ANTHROPIC_API_KEY=… .venv/bin/jobwatch run \
  --terminos "Gerente de Proyectos TI" --ubicacion "Colombia" --cv data/cv.txt
```

El reporte de vacantes nuevas queda en `reportes/AAAA-MM-DD.md`. Para redactar una carta de una oferta guardada, bajo demanda:

```bash
ANTHROPIC_API_KEY=… .venv/bin/jobwatch carta <id_estable>
```

## Programación

Para que corra solo cada día (por ejemplo, 8am), agrega una entrada a `crontab -e`. En WSL2 asegúrate de que el servicio cron esté activo (`sudo service cron start`):

```cron
0 8 * * * cd /ruta/a/jobwatch && ANTHROPIC_API_KEY=… .venv/bin/jobwatch run \
  --terminos "Gerente de Proyectos TI" --ubicacion "Colombia" --cv data/cv.txt
```

Cada corrida reporta solo las vacantes **nuevas** desde la anterior. En Windows, el Programador de Tareas puede invocar el mismo comando dentro de WSL.

## Uso responsable

`jobwatch` está pensado para uso **personal y de bajo volumen** sobre listados de empleo **públicos**:

- Lee únicamente lo que una búsqueda pública ya devuelve — no requiere iniciar sesión para el flujo principal.
- Usa pausas conservadoras entre peticiones y evita el paralelismo agresivo.
- El acceso automatizado puede estar restringido por los Términos de Servicio de un sitio. Eres responsable del uso que le des a esta herramienta. Respeta los términos de cada sitio, su `robots.txt` y sus límites de tasa.

`curl_cffi` se usa por compatibilidad TLS/HTTP de grado navegador con sitios que rechazan clientes no-navegador — no para vulnerar controles de acceso ni autenticación.

## Contribuir

Las contribuciones son bienvenidas — ver [`CONTRIBUTING.md`](CONTRIBUTING.md). Una excelente primera contribución es un conector nuevo para un portal de tu región.

## Licencia

[MIT](LICENSE) © 2026 Juan Urrea & Claude (Anthropic)
