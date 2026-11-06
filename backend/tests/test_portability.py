"""Export complet et réimport dans un nouvel espace (CDC §18, §19 ; EXP01)."""

import hashlib
import io
import json
import zipfile

from conftest import create_space, invite_and_join, register


def _full_space(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner, "Groupe Horizon")
    base = f"/api/spaces/{space['id']}"
    contributor = make_client()
    member = invite_and_join(owner, contributor, space["id"], "moussa@exemple.com", "contributor")
    me = next(m for m in owner.get(f"{base}/members").json() if m["is_me"])

    portfolio = owner.post(
        f"{base}/portfolios", json={"name": "Événements", "color": "blue"}
    ).json()
    entity = owner.post(
        f"{base}/entities", json={"name": "Horizon Dakar", "country": "Sénégal"}
    ).json()
    program = owner.post(f"{base}/programs", json={"name": "Salon Agri"}).json()
    event_type = next(t for t in owner.get(f"{base}/project-types").json() if t["kind"] == "event")
    salon = owner.post(
        f"{base}/projects",
        json={
            "title": "Salon Agri 2026",
            "portfolio_id": portfolio["id"],
            "entity_id": entity["id"],
            "project_type_id": event_type["id"],
            "owner_member_id": me["id"],
            "start_date": "2026-12-01",
            "end_date": "2026-12-03",
            "progress": 30,
            "situation": "Lieu réservé",
            "event": {"venue": "CICAD", "program_id": program["id"], "edition_label": "2026"},
        },
    ).json()
    owner.post(
        f"{base}/projects",
        json={
            "title": "Baromètre",
            "portfolio_id": portfolio["id"],
            "owner_member_id": member["id"],
        },
    )
    owner.post(
        f"{base}/projects/{salon['id']}/tasks",
        json={
            "title": "Signer le traiteur",
            "due_date": "2026-11-20",
            "assignee_label": "Mon assistante",
        },
    )
    pdf = b"%PDF-1.4 contenu de test \xe9"
    owner.post(
        f"{base}/projects/{salon['id']}/documents",
        files={"file": ("Devis traiteur.pdf", pdf, "application/pdf")},
    )
    return owner, contributor, space, base, pdf


def _zip(response):
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    return archive, json.loads(archive.read("pilot-export.json"))


def test_export_contains_data_and_verifiable_files_but_no_secrets(make_client):
    owner, _, _, base, pdf = _full_space(make_client)

    response = owner.get(f"{base}/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    archive, data = _zip(response)
    assert data["format"] == "pilot-export"
    assert {p["title"] for p in data["projects"]} == {"Salon Agri 2026", "Baromètre"}
    assert data["event_details"][0]["venue"] == "CICAD"
    assert data["tasks"][0]["assignee_label"] == "Mon assistante"
    document = data["documents"][0]
    assert archive.read(document["file"]) == pdf
    assert document["sha256"] == hashlib.sha256(pdf).hexdigest()
    raw = archive.read("pilot-export.json").decode()
    for secret in ("password", "token", 'hash"', "storage_key", "invite"):
        assert secret not in raw


def test_only_the_owner_can_export(make_client):
    _, contributor, _, base, _ = _full_space(make_client)
    assert contributor.get(f"{base}/export").status_code == 403


def test_export_reimported_without_duplicates_and_files_checked(make_client):
    """EXP01 : données rapprochées sans doublons ; pièces vérifiées."""
    owner, _, _, base, pdf = _full_space(make_client)
    exported = owner.get(f"{base}/export").content

    result = owner.post(
        "/api/space-imports", files={"file": ("export.zip", exported, "application/zip")}
    )

    assert result.status_code == 201, result.text
    report = result.json()
    assert report["space_name"].startswith("Groupe Horizon (import ")
    assert report["counts"]["projects"] == 2
    assert report["counts"]["tasks"] == 1
    assert report["counts"]["documents"] == 1
    new = f"/api/spaces/{report['space_id']}"
    types = owner.get(f"{new}/project-types").json()
    assert sorted(t["name"] for t in types) == ["Autre", "Mission", "Produit", "Événement"]
    projects = {p["title"]: p for p in owner.get(f"{new}/projects").json()}
    salon = projects["Salon Agri 2026"]
    assert salon["owner"]["name"] == "Aïcha Ndiaye" and salon["owner"]["has_account"] is True
    assert salon["event"]["venue"] == "CICAD"
    assert salon["event"]["program"]["name"] == "Salon Agri"
    assert salon["entity"]["name"] == "Horizon Dakar"
    assert salon["progress"] == 30 and salon["end_date"] == "2026-12-03"
    # Le contributeur n'est pas réinvité : son nom reste, sans compte.
    assert projects["Baromètre"]["owner"] == {
        "member_id": None,
        "name": "Utilisateur Test",
        "has_account": False,
    }
    assert any("ne sont pas invités" in w for w in report["warnings"])
    document = owner.get(f"{new}/documents").json()[0]
    download = owner.get(f"{new}/documents/{document['id']}/download")
    assert download.content == pdf

    again = owner.post(
        "/api/space-imports", files={"file": ("export.zip", exported, "application/zip")}
    )
    assert again.json()["already_imported"] is True
    assert again.json()["space_id"] == report["space_id"]


def test_catalogue_only_export_and_tampered_file_are_reported(make_client):
    owner, _, _, base, _ = _full_space(make_client)
    catalogue_only = owner.get(f"{base}/export?files=false").content
    archive, data = _zip(owner.get(f"{base}/export"))
    tampered = io.BytesIO()
    with zipfile.ZipFile(tampered, "w") as out:
        out.writestr("pilot-export.json", json.dumps(data))
        out.writestr(data["documents"][0]["file"], b"contenu remplace")

    first = owner.post("/api/space-imports", files={"file": ("a.zip", catalogue_only)}).json()
    second = owner.post("/api/space-imports", files={"file": ("b.zip", tampered.getvalue())}).json()

    assert first["counts"]["documents"] == 0
    assert any("catalogue seul" in w for w in first["warnings"])
    assert second["counts"]["documents"] == 0
    assert any("empreinte" in w for w in second["warnings"])


def test_invalid_files_are_refused_clearly(make_client):
    owner = make_client()
    register(owner, "a@exemple.com")

    not_export = owner.post("/api/space-imports", files={"file": ("x.json", b'{"a": 1}')})
    garbage = owner.post("/api/space-imports", files={"file": ("x.zip", b"PK\x03\x04 abime")})
    bad_value = owner.post(
        "/api/space-imports",
        files={
            "file": (
                "x.json",
                json.dumps(
                    {
                        "format": "pilot-export",
                        "format_version": 1,
                        "export_id": "6f1c1b54-0b5e-4bd3-9c55-8f4a0f2a3b11",
                        "space": {"name": "Test", "timezone": "UTC"},
                        "portfolios": [{"id": "p1", "name": "P"}],
                        "projects": [
                            {"id": "x", "title": "T", "portfolio_id": "p1", "status": "inventé"}
                        ],
                    }
                ).encode(),
            )
        },
    )

    assert not_export.status_code == 422
    assert "export PILOT" in not_export.json()["detail"]
    assert garbage.status_code == 422
    assert bad_value.status_code == 422
    assert owner.get("/api/auth/me").json()["spaces"] == []


def test_tampered_values_are_neutralised(make_client):
    owner = make_client()
    register(owner, "a@exemple.com")
    data = {
        "format": "pilot-export",
        "format_version": 1,
        "export_id": "0b6f6f9e-6d43-4b0a-9a0e-2f4f1f0d9a77",
        "space": {"name": "Piège", "timezone": "Mars/Olympus"},
        "portfolios": [{"id": "p1", "name": "P", "color": "url(javascript:x)"}],
        "projects": [
            {
                "id": "x",
                "title": "T",
                "portfolio_id": "p1",
                "status": "to_frame",
                "external_url": "javascript:alert(document.cookie)",
            }
        ],
    }

    report = owner.post(
        "/api/space-imports", files={"file": ("x.json", json.dumps(data).encode())}
    ).json()

    base = f"/api/spaces/{report['space_id']}"
    assert owner.get(base).json()["timezone"] == "UTC"
    assert owner.get(f"{base}/portfolios").json()[0]["color"] == "gray"
    assert owner.get(f"{base}/projects").json()[0]["external_url"] is None


def test_document_versions_survive_export_and_import(make_client):
    owner, _, _, base, pdf = _full_space(make_client)
    first = owner.get(f"{base}/documents").json()[0]
    owner.post(
        f"{base}/documents/{first['id']}/replace",
        files={"file": ("Devis traiteur v2.pdf", b"%PDF-1.4 v2", "application/pdf")},
    )

    report = owner.post(
        "/api/space-imports",
        files={"file": ("export.zip", owner.get(f"{base}/export").content, "application/zip")},
    ).json()

    new = f"/api/spaces/{report['space_id']}"
    current = owner.get(f"{new}/documents").json()
    assert [(d["filename"], d["revision"]) for d in current] == [("Devis traiteur v2.pdf", 2)]
    versions = owner.get(f"{new}/documents/{current[0]['id']}/versions").json()
    assert [v["filename"] for v in versions] == ["Devis traiteur v2.pdf", "Devis traiteur.pdf"]
    assert owner.get(f"{new}/documents/{versions[1]['id']}/download").content == pdf
