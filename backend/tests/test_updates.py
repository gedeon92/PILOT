"""Boîte de mise à jour : parcours complet par l'API (CDC §9, §10, §11 ; UPD01 à UPD05, DOC02)."""

import io
import uuid

from conftest import create_space, invite_and_join, register
from docx import Document as DocxDocument
from openpyxl import Workbook
from pypdf import PdfWriter


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner)
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Projets groupe"}).json()
    return owner, space, base, portfolio


def _project(client, base, portfolio, title, **fields):
    response = client.post(
        f"{base}/projects", json={"title": title, "portfolio_id": portfolio["id"], **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _send(client, base, message="", files=None, **form):
    response = client.post(
        f"{base}/updates", data={"message": message, **form}, files=files or None
    )
    assert response.status_code == 201, response.text
    return response.json()


def _by_title(request):
    return {p["project"]["title"]: p for p in request["proposals"] if p["project"]}


def test_a_message_about_two_projects_gives_two_proposals(make_client):
    """UPD01 : propositions distinctes, avec leur passage source, et rien d'appliqué."""
    owner, _, base, portfolio = _setup(make_client)
    atlas = _project(owner, base, portfolio, "Atlas")
    _project(owner, base, portfolio, "Orion")

    request = _send(
        owner,
        base,
        "Projet Atlas — Statut : en cours. Prochaine étape : valider le budget. "
        "Projet Orion — Blocage : devis fournisseur manquant.",
    )

    proposals = _by_title(request)
    assert set(proposals) == {"Atlas", "Orion"}
    atlas_changes = {c["field"]: c for c in proposals["Atlas"]["changes"]}
    assert atlas_changes["status"]["proposed"] == "En cours"
    assert atlas_changes["status"]["current"] == "À cadrer"
    assert atlas_changes["next_step"]["proposed"] == "valider le budget"
    assert "Statut : en cours" in atlas_changes["status"]["excerpt"]
    orion_changes = {c["field"]: c["proposed"] for c in proposals["Orion"]["changes"]}
    assert orion_changes == {
        "status": "Bloqué",
        "situation": "Blocage : devis fournisseur manquant",
    }
    assert all(p["state"] == "to_validate" for p in request["proposals"])
    # Déposer ne modifie rien.
    assert owner.get(f"{base}/projects/{atlas['id']}").json()["status"] == "to_frame"


def test_keyword_matching_two_editions_asks_which_one(make_client):
    """UPD02 : demande de précision, aucune application arbitraire."""
    owner, _, base, portfolio = _setup(make_client)
    first = _project(owner, base, portfolio, "Forum Agri 2026")
    _project(owner, base, portfolio, "Forum Agri 2027")

    request = _send(owner, base, "Forum Agri — Statut : en préparation")
    proposal = request["proposals"][0]

    assert proposal["state"] == "to_clarify"
    assert proposal["project"] is None
    assert {c["title"] for c in proposal["candidates"]} == {"Forum Agri 2026", "Forum Agri 2027"}
    refused = owner.post(
        f"{base}/proposals/{proposal['id']}/apply", json={"fields": ["status"], "base_version": 1}
    )
    assert refused.status_code == 422

    chosen = owner.post(
        f"{base}/proposals/{proposal['id']}/target", json={"project_id": first["id"]}
    ).json()
    assert chosen["state"] == "to_validate"
    assert chosen["issues"] == []
    applied = owner.post(
        f"{base}/proposals/{proposal['id']}/apply",
        json={"fields": ["status"], "base_version": chosen["base_version"]},
    )
    assert applied.status_code == 200
    assert owner.get(f"{base}/projects/{first['id']}").json()["status"] == "preparing"


def test_objective_percentage_is_not_progress(make_client):
    """UPD03 : « 24 % de l'objectif commercial » ne devient pas un avancement."""
    owner, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, "Atlas")

    request = _send(owner, base, "Atlas — Avancement : 24 % de l'objectif commercial")

    assert request["proposals"] == []
    assert any("objectif" in note for note in request["notes"])


def test_validating_twice_applies_once(make_client):
    """UPD04 : une seule modification métier et un journal cohérent."""
    owner, _, base, portfolio = _setup(make_client)
    atlas = _project(owner, base, portfolio, "Atlas")
    proposal = _send(owner, base, "Atlas — Avancement : 40 %")["proposals"][0]
    body = {"fields": ["progress"], "base_version": proposal["base_version"]}

    first = owner.post(f"{base}/proposals/{proposal['id']}/apply", json=body)
    second = owner.post(f"{base}/proposals/{proposal['id']}/apply", json=body)

    assert first.status_code == second.status_code == 200
    assert second.json()["state"] == "applied"
    project = owner.get(f"{base}/projects/{atlas['id']}").json()
    assert project["progress"] == 40
    assert project["version"] == atlas["version"] + 1
    history = owner.get(f"{base}/projects/{atlas['id']}/history").json()
    assert [h["action"] for h in history].count("project.updated_from_proposal") == 1


def test_target_changed_after_preparation_blocks_until_refresh(make_client):
    """UPD05 : application bloquée jusqu'à actualisation, le texte reste disponible."""
    owner, _, base, portfolio = _setup(make_client)
    atlas = _project(owner, base, portfolio, "Atlas")
    proposal = _send(owner, base, "Atlas — Prochaine étape : signer le contrat")["proposals"][0]
    owner.patch(
        f"{base}/projects/{atlas['id']}", json={"version": atlas["version"], "situation": "Revu"}
    )

    listed = owner.get(f"{base}/updates").json()[0]["proposals"][0]
    blocked = owner.post(
        f"{base}/proposals/{proposal['id']}/apply",
        json={"fields": ["next_step"], "base_version": proposal["base_version"]},
    )
    refreshed = owner.post(f"{base}/proposals/{proposal['id']}/refresh").json()
    applied = owner.post(
        f"{base}/proposals/{proposal['id']}/apply",
        json={"fields": ["next_step"], "base_version": refreshed["base_version"]},
    )

    assert listed["state"] == "conflict"
    assert blocked.status_code == 409
    assert refreshed["state"] == "to_validate"
    assert refreshed["excerpt"] == proposal["excerpt"]
    assert applied.status_code == 200
    project = owner.get(f"{base}/projects/{atlas['id']}").json()
    assert project["next_step"] == "signer le contrat"
    assert project["situation"] == "Revu"


def test_only_checked_fields_are_applied(make_client):
    owner, _, base, portfolio = _setup(make_client)
    atlas = _project(owner, base, portfolio, "Atlas")
    proposal = _send(
        owner, base, "Atlas\nAvancement : 60 %\nÉchéance : 20/11/2026\nResponsable : Aïcha"
    )["proposals"][0]

    owner.post(
        f"{base}/proposals/{proposal['id']}/apply",
        json={"fields": ["due_date", "owner"], "base_version": proposal["base_version"]},
    )

    project = owner.get(f"{base}/projects/{atlas['id']}").json()
    assert project["progress"] is None
    assert project["due_date"] == "2026-11-20"
    assert project["owner"]["name"] == "Aïcha Ndiaye"
    assert project["owner"]["has_account"] is True


def test_scanned_pdf_is_kept_but_not_read(make_client):
    """DOC02 : limite annoncée, aucune lecture fictive."""
    owner, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, "Atlas")
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    pdf = io.BytesIO()
    writer.write(pdf)

    request = _send(owner, base, files=[("files", ("scan.pdf", pdf.getvalue(), "application/pdf"))])

    source = request["sources"][0]
    assert source["extraction"] == "empty"
    assert "OCR" in source["note"]
    assert request["proposals"] == []
    download = owner.get(f"{base}/update-sources/{source['id']}/download")
    assert download.status_code == 200
    assert download.content == pdf.getvalue()


def test_word_and_excel_files_are_read(make_client):
    owner, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, "Atlas")
    _project(owner, base, portfolio, "barometre")
    word = DocxDocument()
    word.add_paragraph("Compte rendu du comité")
    word.add_paragraph("Atlas — Prochaine étape : lancer l'appel d'offres")
    word_file = io.BytesIO()
    word.save(word_file)
    book = Workbook()
    book.active.append(["Projet", "Statut", "Avancement"])
    book.active.append(["barometre", "En cours", "35 %"])
    excel_file = io.BytesIO()
    book.save(excel_file)

    request = _send(
        owner,
        base,
        files=[
            ("files", ("cr.docx", word_file.getvalue(), "application/octet-stream")),
            ("files", ("suivi.xlsx", excel_file.getvalue(), "application/octet-stream")),
        ],
    )

    proposals = _by_title(request)
    assert {c["field"]: c["proposed"] for c in proposals["Atlas"]["changes"]} == {
        "next_step": "lancer l'appel d'offres"
    }
    assert proposals["Atlas"]["source_label"] == "cr.docx"
    assert {c["field"]: c["proposed"] for c in proposals["barometre"]["changes"]} == {
        "status": "En cours",
        "progress": "35 %",
    }


def test_private_requests_stay_private(make_client):
    """Les demandes privées de la propriétaire ne sont pas révélées aux contributeurs."""
    owner, space, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, "Atlas")
    contributor = make_client()
    invite_and_join(owner, contributor, space["id"], "contrib@exemple.com", "contributor")
    private = _send(owner, base, "Atlas — Avancement : 10 %")
    shared = _send(owner, base, "Atlas — Avancement : 20 %", visibility="shared")

    seen = [r["id"] for r in contributor.get(f"{base}/updates").json()]
    hidden = contributor.post(
        f"{base}/proposals/{private['proposals'][0]['id']}/apply",
        json={"fields": ["progress"], "base_version": 1},
    )

    assert seen == [shared["id"]]
    assert hidden.status_code == 404
    assert contributor.get(f"{base}/updates/{private['id']}").status_code == 404


def test_readers_cannot_use_the_update_box(make_client):
    owner, space, base, _ = _setup(make_client)
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")

    response = reader.post(f"{base}/updates", data={"message": "Atlas — Avancement : 5 %"})

    assert response.status_code == 403


def test_same_request_sent_twice_is_kept_once(make_client):
    owner, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, "Atlas")
    key = str(uuid.uuid4())

    first = _send(owner, base, "Atlas — Avancement : 10 %", client_request_id=key)
    again = _send(owner, base, "Atlas — Avancement : 10 %", client_request_id=key)

    assert first["id"] == again["id"]
    assert len(owner.get(f"{base}/updates").json()) == 1


def test_discarded_proposal_changes_nothing(make_client):
    owner, _, base, portfolio = _setup(make_client)
    atlas = _project(owner, base, portfolio, "Atlas")
    proposal = _send(owner, base, "Atlas — Avancement : 90 %")["proposals"][0]

    discarded = owner.post(
        f"{base}/proposals/{proposal['id']}/discard", json={"reason": "Chiffre erroné"}
    ).json()
    late_apply = owner.post(
        f"{base}/proposals/{proposal['id']}/apply",
        json={"fields": ["progress"], "base_version": proposal["base_version"]},
    )

    assert discarded["state"] == "discarded"
    assert discarded["discard_reason"] == "Chiffre erroné"
    assert late_apply.status_code == 409
    assert owner.get(f"{base}/projects/{atlas['id']}").json()["progress"] is None


def test_source_file_joins_project_folder_only_on_request(make_client):
    owner, _, base, portfolio = _setup(make_client)
    atlas = _project(owner, base, portfolio, "Atlas")
    request = _send(
        owner, base, files=[("files", ("Atlas.txt", b"Avancement : 30 %", "text/plain"))]
    )
    assert owner.get(f"{base}/projects/{atlas['id']}/documents").json() == []

    shared = owner.post(
        f"{base}/update-sources/{request['sources'][0]['id']}/share",
        json={"project_id": atlas["id"]},
    )

    assert shared.status_code == 201
    documents = owner.get(f"{base}/projects/{atlas['id']}/documents").json()
    assert [d["filename"] for d in documents] == ["Atlas.txt"]


def test_unknown_project_and_empty_text_are_explained(make_client):
    owner, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, "Atlas")

    unknown = _send(owner, base, "Statut : en cours")
    nothing = _send(owner, base, "Bonjour à tous, merci pour la réunion.")
    up_to_date = _send(owner, base, "Atlas — Statut : à cadrer")

    assert unknown["proposals"][0]["state"] == "to_clarify"
    assert unknown["proposals"][0]["issues"][0].startswith("Projet non identifié")
    assert nothing["proposals"] == []
    assert "aucun projet ni libellé reconnu" in nothing["notes"][0]
    assert up_to_date["proposals"] == []
    assert "déjà à jour" in up_to_date["notes"][0]
