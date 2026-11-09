"""Droits par projet (lot C) : projets privés, rôle propre à un projet, invités extérieurs.
Le CDC (§4) exige que la restriction s'applique à tous les chemins de lecture : liste, fiche,
tâches, documents, téléchargements, liens, alertes, boîte de mise à jour."""

from conftest import create_space, invite_and_join, register

PDF = ("devis.pdf", b"%PDF-1.4 devis", "application/pdf")


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner, "Groupe Horizon")
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Projets"}).json()

    def project(title):
        response = owner.post(
            f"{base}/projects", json={"title": title, "portfolio_id": portfolio["id"]}
        )
        assert response.status_code == 201, response.text
        return response.json()

    return owner, space, base, project


def _access(client, base, project, private, members=()):
    return client.put(
        f"{base}/projects/{project['id']}/access",
        json={"private": private, "members": [{"member_id": m, "role": r} for m, r in members]},
    )


def test_private_project_is_hidden_everywhere_from_non_members(make_client):
    owner, space, base, project = _setup(make_client)
    moussa = make_client()
    invite_and_join(owner, moussa, space["id"], "moussa@exemple.com", "contributor")
    secret = project("Rachat confidentiel")
    open_project = project("Salon Agri")
    task = owner.post(f"{base}/projects/{secret['id']}/tasks", json={"title": "Audit"}).json()
    doc = owner.post(f"{base}/projects/{secret['id']}/documents", files={"file": PDF}).json()
    owner.post(f"{base}/projects/{open_project['id']}/links", json={"project_id": secret["id"]})
    assert _access(owner, base, secret, private=True).status_code == 200

    pid = secret["id"]
    titles = [p["title"] for p in moussa.get(f"{base}/projects").json()]
    assert titles == ["Salon Agri"]
    for path in (
        f"/projects/{pid}",
        f"/projects/{pid}/tasks",
        f"/projects/{pid}/history",
        f"/projects/{pid}/documents",
        f"/projects/{pid}/links",
        f"/tasks/{task['id']}",
        f"/documents/{doc['id']}/download",
        f"/documents/{doc['id']}/versions",
    ):
        assert moussa.get(f"{base}{path}").status_code == 404, path
    assert moussa.get(f"{base}/tasks").json() == []
    assert moussa.get(f"{base}/documents").json() == []
    # Le projet ouvert ne révèle pas son lien vers le projet privé.
    assert moussa.get(f"{base}/projects/{open_project['id']}/links").json() == []
    # Aucune écriture possible non plus.
    assert (
        moussa.post(f"{base}/projects/{pid}/tasks", json={"title": "Intrusion"}).status_code == 404
    )
    patch = moussa.patch(f"{base}/tasks/{task['id']}", json={"version": 1, "status": "done"})
    assert patch.status_code == 404

    # Le propriétaire voit tout, et le projet est marqué privé.
    mine = owner.get(f"{base}/projects/{pid}").json()
    assert mine["private"] is True and mine["my_role"] == "owner"


def test_member_of_private_project_gets_its_role(make_client):
    owner, space, base, project = _setup(make_client)
    moussa = make_client()
    member = invite_and_join(owner, moussa, space["id"], "moussa@exemple.com", "contributor")
    secret = project("Rachat confidentiel")
    assert _access(owner, base, secret, True, [(member["id"], "reader")]).status_code == 200

    seen = moussa.get(f"{base}/projects/{secret['id']}").json()
    assert seen["my_role"] == "reader"
    # Lecteur sur ce projet : il consulte mais ne modifie pas, même s'il contribue ailleurs.
    refused = moussa.post(f"{base}/projects/{secret['id']}/tasks", json={"title": "Non"})
    assert refused.status_code == 403

    _access(owner, base, secret, True, [(member["id"], "contributor")])
    created = moussa.post(f"{base}/projects/{secret['id']}/tasks", json={"title": "Oui"})
    assert created.status_code == 201

    history = owner.get(f"{base}/projects/{secret['id']}/history").json()
    assert any(h["action"] == "project.access_changed" for h in history)


def test_project_role_overrides_space_role_on_open_projects(make_client):
    owner, space, base, project = _setup(make_client)
    fatou = make_client()
    member = invite_and_join(owner, fatou, space["id"], "fatou@exemple.com", "reader")
    salon = project("Salon Agri")
    other = project("Baromètre")
    _access(owner, base, salon, False, [(member["id"], "contributor")])

    # Lectrice de l'espace, mais contributrice du Salon : elle modifie le Salon, pas le reste.
    assert (
        fatou.post(f"{base}/projects/{salon['id']}/tasks", json={"title": "Ok"}).status_code == 201
    )
    assert (
        fatou.post(f"{base}/projects/{other['id']}/tasks", json={"title": "Non"}).status_code == 403
    )
    roles = {p["title"]: p["my_role"] for p in fatou.get(f"{base}/projects").json()}
    assert roles == {"Salon Agri": "contributor", "Baromètre": "reader"}


def test_guest_sees_only_the_projects_given_to_them(make_client):
    owner, space, base, project = _setup(make_client)
    guest = make_client()
    member = invite_and_join(owner, guest, space["id"], "prestataire@agence.com", "guest")
    salon = project("Salon Agri")
    project("Baromètre")

    assert guest.get(f"{base}/projects").json() == []
    _access(owner, base, salon, False, [(member["id"], "contributor")])
    assert [p["title"] for p in guest.get(f"{base}/projects").json()] == ["Salon Agri"]
    assert (
        guest.post(f"{base}/projects/{salon['id']}/tasks", json={"title": "Devis"}).status_code
        == 201
    )

    # Pas d'action à l'échelle de l'espace.
    portfolio = owner.get(f"{base}/portfolios").json()[0]
    new_project = guest.post(
        f"{base}/projects", json={"title": "Le mien", "portfolio_id": portfolio["id"]}
    )
    assert new_project.status_code == 403
    assert guest.get(f"{base}/updates").status_code == 403


def test_only_owners_manage_access(make_client):
    owner, space, base, project = _setup(make_client)
    moussa = make_client()
    member = invite_and_join(owner, moussa, space["id"], "moussa@exemple.com", "contributor")
    salon = project("Salon Agri")

    assert _access(moussa, base, salon, True, [(member["id"], "contributor")]).status_code == 403
    # Tout membre qui voit le projet peut savoir qui y a accès.
    _access(owner, base, salon, False, [(member["id"], "reader")])
    access = moussa.get(f"{base}/projects/{salon['id']}/access").json()
    assert access["private"] is False
    assert [(m["email"], m["role"]) for m in access["members"]] == [
        ("moussa@exemple.com", "reader")
    ]


def test_no_notification_about_a_project_one_cannot_see(make_client):
    owner, space, base, project = _setup(make_client)
    moussa = make_client()
    member = invite_and_join(owner, moussa, space["id"], "moussa@exemple.com", "contributor")
    secret = project("Rachat confidentiel")
    _access(owner, base, secret, True)
    task = owner.post(f"{base}/projects/{secret['id']}/tasks", json={"title": "Audit"}).json()

    owner.post(
        f"{base}/tasks/{task['id']}/comments",
        json={"body": "@Moussa à voir", "mentions": [member["id"]]},
    )
    alerts = moussa.get(f"{base}/alerts").json()["items"]
    assert [a for a in alerts if a["rule"] == "mention"] == []


def test_update_box_does_not_recognise_a_hidden_project(make_client):
    owner, space, base, project = _setup(make_client)
    moussa = make_client()
    invite_and_join(owner, moussa, space["id"], "moussa@exemple.com", "contributor")
    secret = project("Atlas")
    _access(owner, base, secret, True)

    request = moussa.post(
        f"{base}/updates", data={"message": "Projet Atlas — Statut : en cours."}
    ).json()
    assert all(p["project"] is None for p in request["proposals"])
    assert all(c["id"] != secret["id"] for p in request["proposals"] for c in p["candidates"])
