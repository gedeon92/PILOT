from conftest import create_space, register


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Événements"}).json()
    types = {t["kind"]: t for t in owner.get(f"{base}/project-types").json()}
    standard = next(t for t in owner.get(f"{base}/project-types").json() if t["kind"] == "standard")
    return owner, base, portfolio, types["event"], standard


def _create(client, base, portfolio, ptype, **fields):
    response = client.post(
        f"{base}/projects",
        json={
            "title": "Salon",
            "portfolio_id": portfolio["id"],
            "project_type_id": ptype["id"],
            **fields,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_event_details_and_follow_up(make_client):
    owner, base, portfolio, event_type, _ = _setup(make_client)
    program = owner.post(f"{base}/programs", json={"name": "Salon Dakar Tech"}).json()

    project = _create(
        owner,
        base,
        portfolio,
        event_type,
        start_date="2026-11-12",
        end_date="2026-11-13",
        date_certainty="confirmed",
        event={
            "venue": "CICAD",
            "audience": "Décideurs",
            "expected_attendance": 300,
            "program_id": program["id"],
            "edition_label": "2026",
        },
    )

    assert project["event"] == {
        "venue": "CICAD",
        "audience": "Décideurs",
        "expected_attendance": 300,
        "program": {"id": program["id"], "name": "Salon Dakar Tech"},
        "edition_label": "2026",
        "follow_up_until": "2026-11-28",  # J+15 après la fin
    }


def test_event_without_details_or_date(make_client):
    owner, base, portfolio, event_type, _ = _setup(make_client)
    project = _create(owner, base, portfolio, event_type)
    assert project["event"]["venue"] is None
    assert project["event"]["follow_up_until"] is None


def test_standard_project_has_no_event_fields(make_client):
    owner, base, portfolio, _, standard = _setup(make_client)
    project = _create(owner, base, portfolio, standard)
    refused = owner.post(
        f"{base}/projects",
        json={
            "title": "X",
            "portfolio_id": portfolio["id"],
            "project_type_id": standard["id"],
            "event": {"venue": "Ici"},
        },
    )
    assert project["event"] is None
    assert refused.status_code == 422


def test_details_survive_a_type_change(make_client):
    owner, base, portfolio, event_type, standard = _setup(make_client)
    project = _create(owner, base, portfolio, event_type, event={"venue": "CICAD"})
    url = f"{base}/projects/{project['id']}"

    as_standard = owner.patch(url, json={"version": 1, "project_type_id": standard["id"]}).json()
    back = owner.patch(url, json={"version": 2, "project_type_id": event_type["id"]}).json()

    assert as_standard["event"] is None
    assert back["event"]["venue"] == "CICAD"


def test_rescheduling_is_journaled(make_client):
    owner, base, portfolio, event_type, _ = _setup(make_client)
    project = _create(owner, base, portfolio, event_type, start_date="2026-11-12")
    url = f"{base}/projects/{project['id']}"

    owner.patch(
        url, json={"version": 1, "start_date": "2026-12-03", "event": {"venue": "Diamniadio"}}
    )

    entry = owner.get(f"{url}/history").json()[0]
    assert entry["before"]["start_date"] == "2026-11-12"
    assert entry["after"]["start_date"] == "2026-12-03"
    assert entry["after"]["event_venue"] == "Diamniadio"


def test_cancelled_edition_keeps_its_file(make_client):
    """CAL02 : une édition annulée sort du calendrier actif ; son dossier reste consultable."""
    owner, base, portfolio, event_type, _ = _setup(make_client)
    project = _create(
        owner, base, portfolio, event_type, start_date="2026-11-12", event={"edition_label": "2026"}
    )
    owner.post(f"{base}/projects/{project['id']}/tasks", json={"title": "Réserver"})

    cancelled = owner.post(
        f"{base}/projects/{project['id']}/status",
        json={"version": 1, "status": "cancelled", "reason": "Reporté à 2027"},
    ).json()

    assert cancelled["status"] == "cancelled"
    assert cancelled["start_date"] == "2026-11-12"
    assert cancelled["event"]["edition_label"] == "2026"


def test_filters_by_kind_and_program(make_client):
    owner, base, portfolio, event_type, standard = _setup(make_client)
    program = owner.post(f"{base}/programs", json={"name": "Salon"}).json()
    _create(
        owner,
        base,
        portfolio,
        event_type,
        title="Édition 2026",
        event={"program_id": program["id"]},
    )
    _create(owner, base, portfolio, event_type, title="Séminaire")
    _create(owner, base, portfolio, standard, title="Refonte")

    events = owner.get(f"{base}/projects", params={"kind": "event"}).json()
    editions = owner.get(f"{base}/projects", params={"program_id": program["id"]}).json()

    assert sorted(p["title"] for p in events) == ["Séminaire", "Édition 2026"]
    assert [p["title"] for p in editions] == ["Édition 2026"]


def test_program_from_another_space_is_refused(make_client):
    owner, base, portfolio, event_type, _ = _setup(make_client)
    other = make_client()
    register(other, "autre@exemple.com")
    other_base = f"/api/spaces/{create_space(other, 'Autre')['id']}"
    foreign = other.post(f"{other_base}/programs", json={"name": "Étranger"}).json()

    response = owner.post(
        f"{base}/projects",
        json={
            "title": "X",
            "portfolio_id": portfolio["id"],
            "project_type_id": event_type["id"],
            "event": {"program_id": foreign["id"]},
        },
    )

    assert response.status_code == 422
