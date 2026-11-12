# Homologaciones SENA · Ibero

Herramienta interna para los asesores comerciales de la **Corporación Universitaria Iberoamericana (Ibero)**:
consulta qué carreras virtuales puede homologar un egresado SENA, con cuántos créditos, su precio SENA
y un mensaje listo para WhatsApp.

## Qué tiene

- **Homologaciones**: búsqueda tolerante a tildes y errores ("gestion logistica" trae el técnico y el tecnólogo).
  Cada carrera muestra créditos homologados / créditos del programa (%), créditos pendientes, semestres
  estimados por cursar, precio SENA, pago del primer periodo con pronto pago y cohorte.
- **Mensaje listo** para copiar o abrir en WhatsApp, con o sin precios, y **Crear imagen**: un PNG 1080×1350
  con gráficas de lo que homologa cada carrera (para pegar en WhatsApp).
- **Explorar programas**: búsqueda inversa (qué títulos SENA homologan en cada carrera).
- **Precios**: pregrado y posgrado virtual con la lista SENA (precio SENA, pronto pago, pago total) y la
  lista regular (subsidio Ibero, remarketing, precio final). Ofertas listas para WhatsApp y descarga en Excel.
- **Mensajes**: biblioteca de mensajes por programa y para egresados SENA (variable `{cohorte}`).
- **Brochures y pensum**: PDF por pregrado/posgrado, con visor. Se suben desde Administración → Brochures.
- **Capacitación e IA**: guía rápida y asistente (local o con Claude si se configura `ANTHROPIC_API_KEY`).
- **Administración**: precios, mensajes, configuración, piezas gráficas, pensum y carga del acta.

## Datos

| Archivo | Qué es |
|---|---|
| `Actas SENA Ibero.xlsx` | Resumen de homologaciones SENA Ibero. Solo se usan filas de modalidad virtual. Se reemplaza desde Administración. |
| `data/precios.json` | Listas de precios SENA y regular (pregrado y posgrado virtual). |
| `data/mensajes_programas.json`, `data/mensajes_sena.json` | Mensajes guardados. |
| `data/config.json` | Configuración (cohorte por defecto, nombre del asesor, módulos visibles). |
| `data/pensum/pregrado`, `data/pensum/posgrado` | PDF de pensum. Se enlazan solos con cada carrera por nombre. |

Los semestres son una **equivalencia aproximada**: el acta trae créditos y un estimado de semestres pendientes;
el porcentaje siempre se calcula sobre créditos.

## Correr local

```bash
pip install -r requirements.txt
python app.py            # http://localhost:8000
python -m pytest -q      # pruebas
```

## Despliegue

- **Python App (cPanel/LiteSpeed)**: archivo de inicio `passenger_wsgi.py`, objeto `application`.
- **Docker**: `docker compose up -d --build` (copia `.env.example` a `.env`).
- **Gunicorn**: `gunicorn -w 3 -b 0.0.0.0:8000 app:app`.

Persistir entre despliegues: `data/` (incluye acta subida, pensum y backups), `static/piezas/` y `static/brochures/`.

Variables de entorno: ver `.env.example` (`SECRET_KEY`, `APP_USER`, `APP_PASSWORD`, `ADMIN_PASSWORD`,
`SESSION_COOKIE_SECURE`, `ANTHROPIC_API_KEY` opcional).
