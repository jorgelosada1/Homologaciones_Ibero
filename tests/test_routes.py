import pytest

PAGES = ["/", "/dashboard", "/programas", "/mensajes", "/mensajes?nivel=sena", "/mensajes?nivel=pos", "/precios",
         "/precios?nivel=pos", "/piezas", "/brochures", "/capacitacion", "/brochures?nivel=posgrado"]
QUITADOS = ["/presencial", "/simulador", "/whatsapp", "/cruce", "/aguachica", "/parametrizacion", "/flujos"]


def test_login_requerido(app):
    c = app.test_client()
    r = c.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert c.get("/api/homologar?q=x").status_code == 401


def test_login_ok_y_error(app):
    c = app.test_client()
    assert "incorrectos" in c.post("/login", data={"user": "x", "password": "y"}).get_data(as_text=True)
    r = c.post("/login", data={"user": "Innovacion", "password": "0228"})
    assert r.status_code == 302


@pytest.mark.parametrize("path", PAGES)
def test_paginas_cargan(client, path):
    assert client.get(path).status_code == 200


def test_sena_redirige(client):
    r = client.get("/sena?q=salud")
    assert r.status_code == 302 and "nivel=sena" in r.headers["Location"]


def test_api_homologar(client):
    d = client.get("/api/homologar?q=gestion%20logistica&precios=1").get_json()
    assert d["ok"] and d["total_programas"] >= 1 and "Precios Ibero" in d["mensaje_precios"]
    assert "Precio SENA" in d["mensaje"]


def test_api_titulos_fuzzy(client):
    d = client.get("/api/titulos?q=gestion%20logistik").get_json()
    assert any("Logística" in i["titulo"] for i in d["items"])


def test_api_asistente_local(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = client.post("/api/asistente", json={"message": "precio de ingenieria industrial"}).get_json()
    assert d["ok"] and d["source"] == "local" and "Ingeniería Industrial" in d["reply"]


@pytest.mark.parametrize("path", QUITADOS)
def test_modulos_quitados(client, path):
    assert client.get(path).status_code == 404


def test_menu_sin_modulos_quitados(client):
    html = client.get("/").get_data(as_text=True)
    for path in QUITADOS:
        assert f'href="{path}"' not in html
    assert 'href="/brochures"' in html and "Ibero" in html and "Areandina" not in html


def test_modulo_oculto_por_config(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "modulos_ocultos", lambda: {"piezas"})
    r = client.get("/piezas")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")


def test_pensum_pdf(client, tmp_path, monkeypatch):
    import app as app_module
    from core import pensum
    carpeta = tmp_path / "pos"
    carpeta.mkdir()
    (carpeta / "ESPECIALIZACION EN INTELIGENCIA ARTIFICIAL.pdf").write_bytes(b"%PDF-1.4 prueba")
    monkeypatch.setitem(pensum.PENSUM_DIRS, "posgrado", str(carpeta))
    monkeypatch.setitem(app_module.PENSUM_DIRS, "posgrado", str(carpeta))
    nombre = "ESPECIALIZACION EN INTELIGENCIA ARTIFICIAL.pdf"
    r = client.get(f"/brochures/posgrado/archivo/{nombre}")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert client.get("/brochures/posgrado/archivo/../app.py").status_code == 404
    html = client.get("/brochures?nivel=posgrado").get_data(as_text=True)
    assert "Inteligencia Artificial" in html


def test_admin_protegido(client):
    assert client.get("/admin/precios").status_code == 302


def test_admin_precios_guarda(admin):
    import json
    from core.data import DATA_DIR
    import os
    path = os.path.join(DATA_DIR, "precios.json")
    original = open(path, encoding="utf-8").read()
    try:
        r = admin.post("/admin/precios", data={"action": "add", "nivel": "pre", "programa": "Programa de prueba", "valor": "1000",
                                               "valor_final": "900", "subsidio": "", "remarketing": "", "pronto_pago": "",
                                               "cohorte": "1RA COHORTE_27", "valor_sena": "", "cohorte_sena": ""})
        assert r.status_code == 302
        nuevo = json.load(open(path, encoding="utf-8"))[-1]
        assert nuevo["programa"] == "Programa de prueba" and nuevo["valor_sena"] is None and nuevo["cohorte_sena"] is None
    finally:
        open(path, "w", encoding="utf-8").write(original)


def test_admin_paginas(admin):
    for p in ["/admin/dashboard", "/admin/mensajes-comerciales", "/admin/mensajes-sena", "/admin/precios",
              "/admin/piezas", "/admin/brochures", "/admin/config"]:
        assert admin.get(p).status_code == 200, p


def test_csrf_bloquea_post_sin_token(app):
    app.config["CSRF_ENABLED"] = True
    try:
        c = app.test_client()
        with c.session_transaction() as s:
            s["logged_in"] = True
        assert c.post("/api/track", json={"tipo": "copia"}).status_code == 400
        with c.session_transaction() as s:
            s["_csrf_token"] = "abc"
        assert c.post("/api/track", json={"tipo": "copia"}, headers={"X-CSRF-Token": "abc"}).status_code == 200
    finally:
        app.config["CSRF_ENABLED"] = False


def test_path_traversal_piezas(client):
    r = client.get("/piezas/../../app.py")
    assert r.status_code in (302, 404)


def test_404_bonito(client):
    r = client.get("/no-existe")
    assert r.status_code == 404 and "no existe" in r.get_data(as_text=True)


# ---------- Comercial: PLUS, objeciones y simuladores ----------
COMERCIAL = ["/plus", "/plus?p=derecho", "/objeciones", "/simuladores", "/simuladores?programa=Derecho"]


@pytest.mark.parametrize("path", COMERCIAL)
def test_paginas_comerciales_cargan(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/plus", "/objeciones", "/simuladores"])
def test_paginas_comerciales_requieren_login(app, path):
    r = app.test_client().get(path)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_menu_tiene_modulos_comerciales(client):
    html = client.get("/").get_data(as_text=True)
    for path in ("/plus", "/objeciones", "/simuladores"):
        assert f'href="{path}"' in html


def test_modulo_comercial_oculto(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "modulos_ocultos", lambda: {"simuladores"})
    assert client.get("/simuladores").status_code == 302
    assert 'href="/simuladores"' not in client.get("/").get_data(as_text=True)


def test_plus_con_precio_y_sin_cruces(client):
    import app as app_module
    progs = {p["id"]: p for p in app_module.programas_plus()}
    assert len(progs) == 24 and all(p["discurso"] or p.get("aviso") for p in progs.values())
    assert progs["derecho"]["precio"]["programa"] == "Derecho"
    assert progs["ing-sistemas"]["precio"]["fecha_ingreso"] == "Febrero 2027 · 1ra cohorte"
    # Marketing y Negocios Internacionales es presencial: no toma el precio de Negocios Internacionales (virtual)
    assert progs["marketing-ni"]["precio"] is None
    html = client.get("/plus").get_data(as_text=True)
    assert "Ingeniería de Sistemas" in html and "Febrero 2027" in html


def test_simuladores_incrustan_finky_ibero(client):
    html = client.get("/simuladores").get_data(as_text=True)
    assert "universityId=77" in html and "tasa_mensual" in html and "Febrero 2027" in html
