"""Champs personnalisés (étape F4, cahier V2 CHP01–CHP04)."""

from conftest import create_space, invite_and_join, register


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Raissa Proprio")
    space = create_space(owner)
    b = f"/api/spaces/{space['id']}"
    contributor = make_client()
    invite_and_join(owner, contributor, space["id"], "contrib@exemple.com", "contributor")
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")
    pf = owner.post(f"{b}/portfolios", json={"name": "Général"}).json()
    project = owner.post(f"{b}/projects", json={"title": "Atlas", "portfolio_id": pf["id"]}).json()
    other = owner.post(f"{b}/projects", json={"title": "Borée", "portfolio_id": pf["id"]}).json()
    return owner, contributor, reader, b, project, other


def test_catalog_values_and_rules(make_client):
    owner, contributor, reader, b, project, other = _setup(make_client)
    risk = {"label": "Type de risque", "target": "project", "type": "choice"}

    # Seuls les propriétaires gèrent le catalogue ; un choix exige des options.
    assert (
        contributor.post(f"{b}/custom-fields", json={**risk, "options": ["A"]}).status_code == 403
    )
    assert owner.post(f"{b}/custom-fields", json=risk).status_code == 422
    field = owner.post(
        f"{b}/custom-fields", json={**risk, "options": ["Financier", "Juridique"]}
    ).json()
    assert field["key"] == "type_de_risque"
    financier, juridique = field["options"]

    # Un montant exige sa devise.
    budget = {"label": "Budget autorisé", "target": "project", "type": "amount"}
    assert owner.post(f"{b}/custom-fields", json=budget).status_code == 422
    budget = owner.post(f"{b}/custom-fields", json={**budget, "config": {"currency": "EUR"}}).json()
    spent = owner.post(
        f"{b}/custom-fields",
        json={
            "label": "Dépensé",
            "target": "project",
            "type": "amount",
            "config": {"currency": "EUR", "min": 0},
        },
    ).json()
    rate = owner.post(
        f"{b}/custom-fields",
        json={
            "label": "Taux de consommation",
            "target": "project",
            "type": "computed",
            "config": {"formula": {"op": "ratio", "a": spent["id"], "b": budget["id"]}},
        },
    ).json()
    checked = owner.post(
        f"{b}/custom-fields",
        json={"label": "Capacité vérifiée", "target": "project", "type": "boolean"},
    ).json()

    # Un contributeur remplit les valeurs ; un lecteur non.
    url = f"{b}/projects/{project['id']}/custom-values"
    values = {field["id"]: financier["id"], budget["id"]: 0, spent["id"]: 300, checked["id"]: False}
    assert reader.put(url, json={"values": values}).status_code == 403
    saved = contributor.put(url, json={"values": values})
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["values"][checked["id"]] is False  # faux n'est pas vide
    assert rate["id"] not in data["values"]  # budget à 0 : non calculable, pas 100 %
    data = contributor.put(url, json={"values": {budget["id"]: 1200}}).json()
    assert data["values"][rate["id"]] == 25.0
    assert contributor.put(url, json={"values": {rate["id"]: 99}}).status_code == 422
    assert contributor.put(url, json={"values": {spent["id"]: -5}}).status_code == 422
    assert contributor.put(url, json={"values": {field["id"]: "opt_inconnue"}}).status_code == 422

    # Renommer une option et retirer une autre : identifiants et valeurs conservés.
    renamed = owner.patch(
        f"{b}/custom-fields/{field['id']}",
        json={
            "version": field["version"],
            "label": "Nature du risque",
            "options": [
                {"id": financier["id"], "label": "Finances", "active": False},
                {"id": juridique["id"], "label": "Juridique"},
                {"label": "Réputation"},
            ],
        },
    ).json()
    assert renamed["key"] == "type_de_risque"
    assert [o["label"] for o in renamed["options"]] == ["Finances", "Juridique", "Réputation"]
    data = owner.get(f"{b}/projects/{project['id']}/custom-fields").json()
    assert data["values"][field["id"]] == financier["id"]
    # L'option retirée reste acceptée là où elle était choisie, plus pour une nouvelle saisie.
    assert contributor.put(url, json={"values": {field["id"]: financier["id"]}}).status_code == 200
    other_url = f"{b}/projects/{other['id']}/custom-values"
    refused = contributor.put(other_url, json={"values": {field["id"]: financier["id"]}})
    assert refused.status_code == 422

    # Filtres de la liste : valeurs par projet.
    assert owner.get(f"{b}/custom-values").json()[project["id"]][field["id"]] == financier["id"]

    # Journal : clé technique, avant et après lisibles.
    history = owner.get(f"{b}/projects/{project['id']}/history").json()
    entry = next(h for h in history if h["action"] == "project.custom_values")
    assert entry is not None

    # Archiver un champ utilisé par une formule est refusé ; sinon il est archivé, pas effacé.
    assert owner.post(f"{b}/custom-fields/{budget['id']}/archive").status_code == 422
    archived = owner.post(f"{b}/custom-fields/{checked['id']}/archive").json()
    assert archived["archived"] is True and archived["values_count"] == 1
    assert contributor.put(url, json={"values": {checked["id"]: True}}).status_code == 422
    assert owner.post(f"{b}/custom-fields/{checked['id']}/restore").json()["archived"] is False


def test_type_change_previews_and_never_erases(make_client):
    owner, contributor, _reader, b, project, other = _setup(make_client)
    field = owner.post(
        f"{b}/custom-fields",
        json={"label": "Charge prévue", "target": "project", "type": "text"},
    ).json()
    url = lambda p: f"{b}/projects/{p['id']}/custom-values"  # noqa: E731
    contributor.put(url(project), json={"values": {field["id"]: "12"}})
    contributor.put(url(other), json={"values": {field["id"]: "beaucoup"}})

    preview = owner.get(
        f"{b}/custom-fields/{field['id']}/type-preview", params={"type": "number"}
    ).json()
    assert preview["total"] == 2 and preview["convertible"] == 1 and preview["blocked"] == 1
    refused = owner.patch(
        f"{b}/custom-fields/{field['id']}", json={"version": field["version"], "type": "number"}
    )
    assert refused.status_code == 422
    # Rien n'a bougé.
    data = owner.get(f"{b}/projects/{other['id']}/custom-fields").json()
    assert data["values"][field["id"]] == "beaucoup"

    contributor.put(url(other), json={"values": {field["id"]: "7,5"}})
    changed = owner.patch(
        f"{b}/custom-fields/{field['id']}", json={"version": field["version"], "type": "number"}
    )
    assert changed.status_code == 200, changed.text
    assert (
        owner.get(f"{b}/projects/{other['id']}/custom-fields").json()["values"][field["id"]] == 7.5
    )


def test_task_fields_project_scope_and_hiding(make_client):
    owner, contributor, reader, b, project, other = _setup(make_client)
    local = owner.post(
        f"{b}/custom-fields",
        json={
            "label": "Lieu de stockage",
            "target": "task",
            "type": "text",
            "project_id": project["id"],
        },
    ).json()
    who = owner.post(
        f"{b}/custom-fields",
        json={"label": "Valideur", "target": "task", "type": "person"},
    ).json()
    task = contributor.post(f"{b}/projects/{project['id']}/tasks", json={"title": "Devis"}).json()
    other_task = contributor.post(
        f"{b}/projects/{other['id']}/tasks", json={"title": "Salle"}
    ).json()
    members = owner.get(f"{b}/members").json()
    member_id = next(m["id"] for m in members if m["email"] == "contrib@exemple.com")

    saved = contributor.put(
        f"{b}/tasks/{task['id']}/custom-values",
        json={"values": {local["id"]: "Entrepôt B", who["id"]: member_id}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["task_values"][task["id"]][local["id"]] == "Entrepôt B"
    # Le champ limité au projet Atlas ne concerne pas Borée.
    refused = contributor.put(
        f"{b}/tasks/{other_task['id']}/custom-values", json={"values": {local["id"]: "X"}}
    )
    assert refused.status_code == 422
    assert [
        f["key"] for f in owner.get(f"{b}/projects/{other['id']}/custom-fields").json()["fields"]
    ] == ["valideur"]
    # Une personne inconnue est refusée.
    bad = contributor.put(
        f"{b}/tasks/{task['id']}/custom-values",
        json={"values": {who["id"]: "00000000-0000-0000-0000-000000000000"}},
    )
    assert bad.status_code == 422

    # Masquer un champ dans un projet (droit de modifier le projet).
    hide = f"{b}/projects/{project['id']}/custom-fields/hidden"
    assert reader.put(hide, json={"field_ids": [who["id"]]}).status_code == 403
    hidden = contributor.put(hide, json={"field_ids": [who["id"]]}).json()
    assert hidden["hidden_ids"] == [who["id"]]
    # Les valeurs restent : masquer n'efface rien.
    assert hidden["task_values"][task["id"]][who["id"]] == member_id


def test_fields_and_values_survive_export_and_import(make_client):
    owner, contributor, _reader, b, project, other = _setup(make_client)
    choice = owner.post(
        f"{b}/custom-fields",
        json={
            "label": "Priorité métier",
            "target": "project",
            "type": "choice",
            "options": ["Haute"],
        },
    ).json()
    a = owner.post(
        f"{b}/custom-fields",
        json={"label": "Prévu", "target": "project", "type": "number"},
    ).json()
    c = owner.post(
        f"{b}/custom-fields",
        json={"label": "Réel", "target": "project", "type": "number"},
    ).json()
    owner.post(
        f"{b}/custom-fields",
        json={
            "label": "Écart",
            "target": "project",
            "type": "computed",
            "config": {"formula": {"op": "difference", "a": a["id"], "b": c["id"]}},
        },
    )
    owner.put(
        f"{b}/projects/{project['id']}/custom-values",
        json={"values": {choice["id"]: choice["options"][0]["id"], a["id"]: 10, c["id"]: 4}},
    )
    owner.put(f"{b}/projects/{other['id']}/custom-fields/hidden", json={"field_ids": [a["id"]]})

    report = owner.post(
        "/api/space-imports",
        files={"file": ("export.zip", owner.get(f"{b}/export").content, "application/zip")},
    ).json()
    assert report["counts"]["custom_fields"] == 4
    assert report["counts"]["custom_field_values"] == 3
    new = f"/api/spaces/{report['space_id']}"
    projects = {p["title"]: p for p in owner.get(f"{new}/projects").json()}
    data = owner.get(f"{new}/projects/{projects['Atlas']['id']}/custom-fields").json()
    by_key = {f["key"]: f for f in data["fields"]}
    assert data["values"][by_key["priorite_metier"]["id"]] == choice["options"][0]["id"]
    assert data["values"][by_key["ecart"]["id"]] == 6
    hidden = owner.get(f"{new}/projects/{projects['Borée']['id']}/custom-fields").json()
    assert hidden["hidden_ids"] == [by_key["prevu"]["id"]]
