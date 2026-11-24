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
- **Precios**: pregrado y posgrado virtual con la lista SENA (precio SENA, pronto pago, pago total) y la
  lista regular (subsidio Ibero, remarketing, precio final). Ofertas listas para WhatsApp y descarga en Excel.
- **Mensajes**: biblioteca de mensajes por programa y para egresados SENA (variable `{cohorte}`).
- **Fechas de ingreso**: la vigencia de la lista de precios se muestra como fecha
  (`1RA COHORTE_27` → *Febrero 2027 · 1ra cohorte*; 2da abril, 3ra junio, 4ta agosto, 5ta octubre).
- **PLUS pregrados**: ficha de cada pregrado con discurso (copiar), PLUS y ventajas, perfil profesional,
  materias, campo laboral, objeción frecuente y precio vigente de la lista.
- **Objeciones y filtros**: objeciones generales (con la *pregunta para continuar*), por nivel, por pregrado y
  por posgrado; preguntas filtro en 7 pasos con casillas y clasificador de lead (caliente / tibio / frío).
- **Simuladores de crédito**: Finky (simulador oficial incrustado, Ibero ya seleccionada) y Rombo cuota fija
  (15 % de cuota inicial, fee $69.000, 1,85 % mensual, 4, 6 o 12 cuotas) con precarga del valor del semestre
  desde la lista de precios y resumen para WhatsApp.
- **Brochures y pensum**: PDF por pregrado/posgrado, con visor. Se suben desde Administración → Brochures.
- **Administración**: precios, mensajes, configuración, piezas gráficas, pensum y carga del acta.

## Marca

Sigue el Manual de Marca IBERO 2026: tipografía **Montserrat** (extra bold en títulos, bold en subtítulos,
regular en texto), colores **#4A4848** (neutral black U), **#DFC14E** (7404 U), **#D0AB4B** (110 U) y blanco,
y acentos con los colores por facultad. El logo oficial está en `static/brand/` (`logo-ibero.png` horizontal con
endoso PFU, `simbolo.png` y `favicon.png`); sobre el menú gris se usa la versión positiva en recuadro blanco.

## Datos

| Archivo | Qué es |
|---|---|
| `Actas SENA Ibero.xlsx` | Resumen de homologaciones SENA Ibero. Solo se usan filas de modalidad virtual. Se reemplaza desde Administración. |
| `data/precios.json` | Listas de precios SENA y regular (pregrado y posgrado virtual). |
| `data/mensajes_programas.json`, `data/mensajes_sena.json` | Mensajes guardados. |
| `data/config.json` | Configuración (cohorte por defecto, nombre del asesor, módulos visibles). |
| `data/plus_pregrados.json` | PLUS de los 24 pregrados (desde `PLUS_PREGRADOS_IBERO.xlsx`). |
| `data/comercial.json` | Fechas de ingreso 2027, objeciones, preguntas filtro y parámetros de los simuladores Finky y Rombo. |
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
`SESSION_COOKIE_SECURE`).
