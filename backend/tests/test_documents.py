from conftest import create_space, invite_and_join, register

PDF = b"%PDF-1.4 contenu de test " * 100


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner)
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Événements"}).json()
    project = owner.post(
        f"{base}/projects", json={"title": "Salon", "portfolio_id": portfolio["id"]}
    ).json()
    return owner, space, base, project


def _upload(client, base, project, name="Compte rendu.pdf", data=PDF, ctype="application/pdf"):
    return client.post(
        f"{base}/projects/{project['id']}/documents", files={"file": (name, data, ctype)}
    )


def test_upload_then_download_returns_the_same_file(make_client):
    """DOC01 : un fichier enregistré puis téléchargé est identique, en pièce jointe."""
    owner, _, base, project = _setup(make_client)

    uploaded = _upload(owner, base, project)
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["filename"] == "Compte rendu.pdf"
    assert document["size_bytes"] == len(PDF)
    assert document["uploaded_by"] == "Aïcha Ndiaye"

    download = owner.get(f"{base}/documents/{document['id']}/download")
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"

    listed = owner.get(f"{base}/projects/{project['id']}/documents").json()
    assert [d["id"] for d in listed] == [document["id"]]


def test_file_is_available_from_another_device(make_client):
    owner, _, base, project = _setup(make_client)
    document = _upload(owner, base, project).json()

    other_device = make_client()
    other_device.post(
        "/api/auth/login", json={"email": "proprio@exemple.com", "password": "mot-de-passe-solide"}
    )

    assert other_device.get(f"{base}/documents/{document['id']}/download").content == PDF


def test_too_large_or_empty_file_is_refused(make_client):
    owner, _, base, project = _setup(make_client)

    too_large = _upload(owner, base, project, data=b"x" * (4 * 1024 * 1024 + 1))
    empty = _upload(owner, base, project, data=b"")

    assert too_large.status_code == 413
    assert empty.status_code == 422
    assert owner.get(f"{base}/projects/{project['id']}/documents").json() == []


def test_filename_is_only_a_label(make_client):
    owner, _, base, project = _setup(make_client)
    document = _upload(owner, base, project, name="..\\..\\dossier/../rapport.pdf").json()
    assert document["filename"] == "rapport.pdf"


def test_reader_downloads_but_cannot_upload_or_archive(make_client):
    owner, space, base, project = _setup(make_client)
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")
    document = _upload(owner, base, project).json()

    assert reader.get(f"{base}/documents/{document['id']}/download").status_code == 200
    assert _upload(reader, base, project).status_code == 403
    assert reader.post(f"{base}/documents/{document['id']}/archive").status_code == 403


def test_documents_are_isolated_between_spaces(make_client):
    owner, _, base, project = _setup(make_client)
    document = _upload(owner, base, project).json()
    other = make_client()
    register(other, "autre@exemple.com")
    other_base = f"/api/spaces/{create_space(other, 'Autre')['id']}"

    assert other.get(f"{base}/documents/{document['id']}/download").status_code == 404
    assert other.get(f"{other_base}/documents/{document['id']}/download").status_code == 404
    assert make_client().get(f"{base}/documents/{document['id']}/download").status_code == 401


def test_archived_document_is_hidden_and_journaled(make_client):
    owner, _, base, project = _setup(make_client)
    document = _upload(owner, base, project).json()

    archived = owner.post(f"{base}/documents/{document['id']}/archive")

    assert archived.json()["archived"] is True
    assert owner.get(f"{base}/projects/{project['id']}/documents").json() == []
    assert owner.get(f"{base}/documents").json() == []
    actions = [h["action"] for h in owner.get(f"{base}/projects/{project['id']}/history").json()]
    assert actions[:2] == ["document.archived", "document.uploaded"]


def test_space_document_list(make_client):
    owner, _, base, project = _setup(make_client)
    _upload(owner, base, project, name="Budget.xlsx", ctype="application/vnd.ms-excel")
    _upload(owner, base, project, name="Programme.pdf")

    found = owner.get(f"{base}/documents", params={"q": "budget"}).json()

    assert [(d["filename"], d["project_title"]) for d in found] == [("Budget.xlsx", "Salon")]


def test_clean_filename_removes_control_characters():
    from pilot_api.routers.documents import clean_filename

    assert clean_filename("rap\x00port\n.pdf") == "rapport.pdf"
    assert clean_filename("   ") == "document"
    assert len(clean_filename("a" * 300 + ".pdf")) <= 255


def test_replace_keeps_the_previous_version(make_client):
    """Un remplacement crée la version 2 ; la version 1 reste téléchargeable et au journal."""
    owner, _, base, project = _setup(make_client)
    first = _upload(owner, base, project, name="Budget v1.pdf").json()
    new_content = b"%PDF-1.4 budget revu " * 50

    replaced = owner.post(
        f"{base}/documents/{first['id']}/replace",
        files={"file": ("Budget v2.pdf", new_content, "application/pdf")},
    )

    assert replaced.status_code == 201, replaced.text
    second = replaced.json()
    assert (second["filename"], second["revision"], second["replaced_at"]) == (
        "Budget v2.pdf",
        2,
        None,
    )
    listed = owner.get(f"{base}/projects/{project['id']}/documents").json()
    assert [d["id"] for d in listed] == [second["id"]]
    assert [d["id"] for d in owner.get(f"{base}/documents").json()] == [second["id"]]

    versions = owner.get(f"{base}/documents/{second['id']}/versions").json()
    assert [(v["revision"], v["replaced_at"] is None) for v in versions] == [(2, True), (1, False)]
    assert owner.get(f"{base}/documents/{first['id']}/download").content == PDF
    assert owner.get(f"{base}/documents/{second['id']}/download").content == new_content

    actions = [h["action"] for h in owner.get(f"{base}/projects/{project['id']}/history").json()]
    assert actions[0] == "document.replaced"


def test_only_the_current_version_can_be_replaced_or_archived(make_client):
    owner, _, base, project = _setup(make_client)
    first = _upload(owner, base, project).json()
    owner.post(
        f"{base}/documents/{first['id']}/replace",
        files={"file": ("v2.pdf", PDF + b"2", "application/pdf")},
    )

    again = owner.post(
        f"{base}/documents/{first['id']}/replace",
        files={"file": ("v3.pdf", PDF + b"3", "application/pdf")},
    )
    archive_old = owner.post(f"{base}/documents/{first['id']}/archive")

    assert again.status_code == 409
    assert archive_old.status_code == 409


def test_reader_cannot_replace(make_client):
    owner, space, base, project = _setup(make_client)
    document = _upload(owner, base, project).json()
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")

    refused = reader.post(
        f"{base}/documents/{document['id']}/replace",
        files={"file": ("v2.pdf", PDF, "application/pdf")},
    )
    versions = reader.get(f"{base}/documents/{document['id']}/versions")

    assert refused.status_code == 403
    assert versions.status_code == 200
