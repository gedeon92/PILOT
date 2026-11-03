from conftest import PASSWORD, register


def test_register_opens_a_session(make_client):
    client = make_client()

    body = register(client, "Aicha@Exemple.com", "Aïcha Ndiaye")

    assert body["user"]["email"] == "aicha@exemple.com"
    assert body["spaces"] == []
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["display_name"] == "Aïcha Ndiaye"


def test_session_cookie_is_http_only(make_client):
    client = make_client()
    response = client.post(
        "/api/auth/register",
        json={"email": "a@exemple.com", "password": PASSWORD, "display_name": "A"},
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_register_rejects_duplicate_email(make_client):
    register(make_client(), "a@exemple.com")
    response = make_client().post(
        "/api/auth/register",
        json={"email": "A@exemple.com", "password": PASSWORD, "display_name": "Autre"},
    )
    assert response.status_code == 409


def test_register_rejects_short_password(make_client):
    response = make_client().post(
        "/api/auth/register",
        json={"email": "a@exemple.com", "password": "court", "display_name": "A"},
    )
    assert response.status_code == 422


def test_login_and_logout(make_client):
    register(make_client(), "a@exemple.com")
    client = make_client()

    wrong = client.post("/api/auth/login", json={"email": "a@exemple.com", "password": "faux"})
    unknown = client.post("/api/auth/login", json={"email": "x@exemple.com", "password": "faux"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]

    ok = client.post("/api/auth/login", json={"email": "A@exemple.com", "password": PASSWORD})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_me_requires_a_session(make_client):
    assert make_client().get("/api/auth/me").status_code == 401


def test_write_without_csrf_header_is_refused(make_client):
    client = make_client()
    register(client, "a@exemple.com")
    response = client.post("/api/spaces", json={"name": "Espace"}, headers={"X-PILOT-CSRF": ""})
    assert response.status_code == 403
