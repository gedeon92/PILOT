"""Assistant IA (lot E) : droits, propositions, validation, conflits, limites.

L'API d'Anthropic est remplacée par un faux client scripté : aucun appel réel, aucun coût.
"""

import copy
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from conftest import create_space, invite_and_join, register
from sqlalchemy.orm import sessionmaker

from pilot_api.ai import assistant
from pilot_api.config import get_settings
from pilot_api.main import app
from pilot_api.routers.ai import get_session_opener


class FakeClaude:
    """Chaque appel reçoit les paramètres envoyés et renvoie la réponse suivante du script."""

    def __init__(self, script: list[Callable[[dict], Any]]):
        self.script = list(script)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **params: Any) -> Any:
        self.calls.append(copy.deepcopy(params))
        step = self.script.pop(0)
        return step(params)


def reply(text: str) -> Callable[[dict], Any]:
    return lambda _p: SimpleNamespace(
        content=[{"type": "text", "text": text}],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )


def call(name: str, args: dict | Callable[[], dict], call_id: str = "t1") -> Callable:
    def _step(_p: dict) -> Any:
        return SimpleNamespace(
            content=[
                {"type": "text", "text": "Je regarde."},
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": args() if callable(args) else args,
                },
            ],
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )

    return _step


@pytest.fixture
def ai(engine, monkeypatch) -> Iterator[Callable[[list], FakeClaude]]:
    factory = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def _open():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session_opener] = lambda: _open
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "cle-de-test")
    holder: dict[str, FakeClaude] = {}

    def _install(script: list) -> FakeClaude:
        fake = FakeClaude(script)
        holder["fake"] = fake
        monkeypatch.setattr(assistant, "client_factory", lambda: fake)
        return fake

    yield _install
    app.dependency_overrides.pop(get_session_opener, None)


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@pilot-essai.dev", "Raissa")
    space = create_space(owner)
    sid = space["id"]
    b = f"/api/spaces/{sid}"
    pf = owner.post(f"{b}/portfolios", json={"name": "Événements"}).json()
    project = owner.post(f"{b}/projects", json={"title": "Salon Agri", "portfolio_id": pf["id"]})
    return owner, sid, b, pf, project.json()


def _enable(owner, b):
    r = owner.put(f"{b}/ai/status", json={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True


def test_off_by_default_and_owner_only_toggle(make_client, ai, monkeypatch):
    owner, sid, b, _pf, _p = _setup(make_client)
    member = make_client()
    invite_and_join(owner, member, sid, "contrib@pilot-essai.dev", "contributor")

    status = owner.get(f"{b}/ai/status").json()
    assert status == {
        "available": True,
        "enabled": False,
        "can_toggle": True,
        "daily_limit": get_settings().ai_daily_limit,
        "used_today": 0,
    }
    assert member.get(f"{b}/ai/status").json()["can_toggle"] is False
    assert member.put(f"{b}/ai/status", json={"enabled": True}).status_code == 403
    off = member.post(f"{b}/ai/conversations", json={"text": "Bonjour"})
    assert off.status_code == 403

    _enable(owner, b)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    assert owner.get(f"{b}/ai/status").json()["available"] is False
    assert owner.post(f"{b}/ai/conversations", json={"text": "Bonjour"}).status_code == 503


def test_proposal_is_applied_only_after_click(make_client, ai):
    owner, sid, b, _pf, project = _setup(make_client)
    _enable(owner, b)
    member = make_client()
    invite_and_join(owner, member, sid, "contrib@pilot-essai.dev", "contributor")
    fake = ai(
        [
            call(
                "proposer_creation_tache",
                {
                    "projet_id": project["id"],
                    "title": "Réserver la salle",
                    "due_date": "2026-12-01",
                },
            ),
            reply("Je vous propose une tâche : validez-la ci-dessous."),
        ]
    )

    r = member.post(f"{b}/ai/conversations", json={"text": "Ajoute une tâche réserver la salle"})
    assert r.status_code == 201, r.text
    conv = member.get(f"{b}/ai/conversations/{r.json()['id']}").json()
    assert conv["status"] == "idle"
    assert [t["role"] for t in conv["turns"]] == ["user", "assistant"]
    action = conv["turns"][1]["actions"][0]
    assert action["state"] == "pending"
    assert action["summary"] == "Créer la tâche « Réserver la salle » dans le projet « Salon Agri »"
    assert {"field": "Échéance", "before": "", "after": "01/12/2026"} in action["changes"]
    assert action["project_id"] == project["id"]
    # Le résultat de l'outil dit bien à l'assistant que rien n'est appliqué.
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert "rien n'est encore appliqué" in tool_result["content"]
    assert "is_error" not in tool_result
    # Contexte transmis : rôle et date du jour, règles de sécurité.
    assert "contributeur" in fake.calls[0]["system"][1]["text"]
    assert "jamais des instructions" in fake.calls[0]["system"][0]["text"]

    tasks = owner.get(f"{b}/projects/{project['id']}/tasks").json()
    assert tasks == []

    # Les propositions des autres restent privées.
    assert owner.get(f"{b}/ai/conversations/{conv['id']}").status_code == 404
    assert owner.post(f"{b}/ai/actions/{action['id']}/apply").status_code == 404

    applied = member.post(f"{b}/ai/actions/{action['id']}/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["state"] == "applied"
    assert applied.json()["result"] == "Tâche « Réserver la salle » créée."
    tasks = owner.get(f"{b}/projects/{project['id']}/tasks").json()
    assert [(t["title"], t["due_date"]) for t in tasks] == [("Réserver la salle", "2026-12-01")]
    # Journal habituel, au nom de la personne qui a validé.
    history = owner.get(f"{b}/projects/{project['id']}/history").json()
    assert any(h["action"] == "task.created" for h in history)

    again = member.post(f"{b}/ai/actions/{action['id']}/apply")
    assert again.status_code == 409
    assert len(owner.get(f"{b}/projects/{project['id']}/tasks").json()) == 1
    assert member.get(f"{b}/ai/status").json()["used_today"] == 1


def test_reader_cannot_change_anything_through_the_assistant(make_client, ai):
    owner, sid, b, _pf, project = _setup(make_client)
    _enable(owner, b)
    reader = make_client()
    invite_and_join(owner, reader, sid, "lecteur@pilot-essai.dev", "reader")
    fake = ai(
        [
            call("proposer_creation_tache", {"projet_id": project["id"], "title": "Intrusion"}),
            reply("Votre rôle ne permet pas de modifier ce projet."),
        ]
    )
    r = reader.post(f"{b}/ai/conversations", json={"text": "Crée une tâche"})
    assert r.status_code == 201, r.text
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "consulter, pas de modifier" in result["content"]
    conv = reader.get(f"{b}/ai/conversations/{r.json()['id']}").json()
    assert conv["turns"][1]["actions"] == []


def test_conflict_when_task_changed_meanwhile_and_reject(make_client, ai):
    owner, _sid, b, _pf, project = _setup(make_client)
    _enable(owner, b)
    task = owner.post(
        f"{b}/projects/{project['id']}/tasks", json={"title": "Envoyer les invitations"}
    ).json()
    ai(
        [
            call(
                "proposer_modification_tache",
                {"tache_id": task["id"], "modifications": {"status": "done"}},
            ),
            call(
                "proposer_modification_tache",
                {"tache_id": task["id"], "modifications": {"status": "cancelled"}},
                "t2",
            ),
            reply("Deux propositions."),
        ]
    )
    conv = owner.post(f"{b}/ai/conversations", json={"text": "Termine les invitations"}).json()
    first, second = owner.get(f"{b}/ai/conversations/{conv['id']}").json()["turns"][1]["actions"]
    assert first["summary"] == "Modifier la tâche « Envoyer les invitations »"
    assert first["changes"] == [{"field": "Statut", "before": "À faire", "after": "Terminée"}]
    assert second["summary"] == "Annuler la tâche « Envoyer les invitations »"
    assert first["task_id"] == task["id"] and first["project_id"] == project["id"]

    # Quelqu'un modifie la tâche entre-temps : la proposition n'écrase rien.
    owner.patch(
        f"{b}/tasks/{task['id']}", json={"version": task["version"], "title": "Invitations"}
    )
    conflict = owner.post(f"{b}/ai/actions/{first['id']}/apply").json()
    assert conflict["state"] == "conflict"
    assert "modifiée depuis la proposition" in conflict["result"]
    current = owner.get(f"{b}/tasks/{task['id']}").json()["task"]
    assert current["status"] == "todo"

    rejected = owner.post(f"{b}/ai/actions/{second['id']}/reject").json()
    assert rejected["state"] == "rejected"
    assert owner.post(f"{b}/ai/actions/{second['id']}/apply").status_code == 409


def test_project_status_needs_reason_and_read_tools(make_client, ai):
    owner, _sid, b, pf, project = _setup(make_client)
    _enable(owner, b)
    fake = ai(
        [
            call("rechercher_projets", {"texte": "agri"}),
            call("lister_referentiels", {}, "t2"),
            call(
                "proposer_changement_statut_projet",
                {"projet_id": project["id"], "statut": "cancelled"},
                "t3",
            ),
            call(
                "proposer_changement_statut_projet",
                {"projet_id": project["id"], "statut": "cancelled", "motif": "Salon reporté"},
                "t4",
            ),
            reply("Je propose d'annuler le projet."),
        ]
    )
    conv = owner.post(f"{b}/ai/conversations", json={"text": "Supprime le salon"}).json()
    found = fake.calls[1]["messages"][-1]["content"][0]["content"]
    assert "Salon Agri" in found and '"total": 1' in found
    refs = fake.calls[2]["messages"][-1]["content"][0]["content"]
    assert pf["id"] in refs and "Raissa" in refs
    missing = fake.calls[3]["messages"][-1]["content"][0]
    assert missing["is_error"] is True and "motif" in missing["content"]
    action = owner.get(f"{b}/ai/conversations/{conv['id']}").json()["turns"][1]["actions"][0]
    assert action["summary"] == "Annuler le projet « Salon Agri »"
    done = owner.post(f"{b}/ai/actions/{action['id']}/apply").json()
    assert done["state"] == "applied", done
    assert owner.get(f"{b}/projects/{project['id']}").json()["status"] == "cancelled"


def test_api_error_and_daily_limit(make_client, ai, monkeypatch):
    owner, _sid, b, _pf, _project = _setup(make_client)
    _enable(owner, b)
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def fail(_p):
        raise anthropic.RateLimitError(
            "trop", response=httpx2.Response(429, request=request), body=None
        )

    ai([fail, reply("Bonjour !")])
    conv = owner.post(f"{b}/ai/conversations", json={"text": "Bonjour"}).json()
    detail = owner.get(f"{b}/ai/conversations/{conv['id']}").json()
    assert detail["status"] == "idle"
    assert detail["turns"][-1]["error"] is True
    assert "sollicité" in detail["turns"][-1]["text"]

    again = owner.post(f"{b}/ai/conversations/{conv['id']}/messages", json={"text": "Bonjour"})
    assert again.status_code == 200, again.text
    turns = owner.get(f"{b}/ai/conversations/{conv['id']}").json()["turns"]
    assert turns[-1]["text"] == "Bonjour !"

    monkeypatch.setattr(get_settings(), "ai_daily_limit", 2)
    limited = owner.post(f"{b}/ai/conversations/{conv['id']}/messages", json={"text": "Encore"})
    assert limited.status_code == 429
    assert owner.delete(f"{b}/ai/conversations/{conv['id']}").status_code == 204
    assert owner.get(f"{b}/ai/conversations").json() == []


def test_a_complete_project_is_proposed_in_one_card_and_created_in_one_click(make_client, ai):
    owner, _sid, b, pf, _project = _setup(make_client)
    _enable(owner, b)
    complete = {
        "projet": {
            "title": "Salon Agri 2027",
            "portfolio_id": pf["id"],
            "start_date": "2027-03-01",
            "next_step": "Réserver la salle",
        },
        "sections": ["Préparation", "Exécution"],
        "taches": [
            {
                "title": "Réserver la salle",
                "section": "Préparation",
                "due_date": "2027-02-10",
                "priority": "urgent",
                "assignee_label": "Mon assistante",
                "sous_taches": ["Comparer trois devis", "Visiter la salle"],
            },
            {"title": "Accueillir les exposants", "section": "Exécution"},
        ],
        "jalons": [
            {
                "title": "Salle confirmée",
                "due_date": "2027-02-15",
                "criterion": "Contrat signé",
                "taches": ["Réserver la salle"],
            }
        ],
        "decisions": [
            {
                "statement": "Le salon dure deux jours",
                "executor_label": "Mon assistante",
                "due_date": "2027-01-15",
                "criterion": "Dates publiées sur le site",
            },
            {"statement": "Choisir un traiteur local"},
        ],
    }
    bad = {**complete, "taches": [{"title": "X", "section": "Inconnue"}]}
    fake = ai(
        [
            call("proposer_projet_complet", bad),
            call("proposer_projet_complet", complete, "t2"),
            reply("Je vous propose le projet complet : validez-le ci-dessous."),
        ]
    )
    conv = owner.post(f"{b}/ai/conversations", json={"text": "Crée le salon 2027 complet"}).json()
    refused = fake.calls[1]["messages"][-1]["content"][0]
    assert refused["is_error"] is True and "section inconnue" in refused["content"]

    action = owner.get(f"{b}/ai/conversations/{conv['id']}").json()["turns"][1]["actions"][0]
    assert action["summary"] == (
        "Créer le projet complet « Salon Agri 2027 » "
        "(2 section(s), 2 tâche(s), 1 jalon(s), 2 décision(s))"
    )
    fields = [c["field"] for c in action["changes"]]
    assert fields.count("Tâche") == 2 and "Jalon" in fields and fields.count("Décision") == 2
    assert all(p["title"] != "Salon Agri 2027" for p in owner.get(f"{b}/projects").json())

    applied = owner.post(f"{b}/ai/actions/{action['id']}/apply").json()
    assert applied["state"] == "applied", applied
    assert applied["result"] == (
        "Projet « Salon Agri 2027 » créé avec 2 sections, 2 tâches, 2 sous-tâches, 1 jalons, "
        "2 décisions."
    )
    project = next(p for p in owner.get(f"{b}/projects").json() if p["title"] == "Salon Agri 2027")
    sections = owner.get(f"{b}/projects/{project['id']}/sections").json()
    assert [s["title"] for s in sections] == ["Préparation", "Exécution"]
    tasks = owner.get(f"{b}/projects/{project['id']}/tasks").json()
    room = next(t for t in tasks if t["title"] == "Réserver la salle")
    assert room["section_id"] == sections[0]["id"] and room["priority"] == "urgent"
    assert room["subtasks_total"] == 2
    milestone = owner.get(f"{b}/projects/{project['id']}/milestones").json()[0]
    assert [t["title"] for t in milestone["tasks"]] == ["Réserver la salle"]
    decisions = owner.get(f"{b}/decisions?project_id={project['id']}").json()
    assert sorted(d["state"] for d in decisions) == ["draft", "open"]
    # La carte ouvre la fiche du projet créé.
    assert applied["project_id"] == project["id"]


def test_the_complete_project_can_be_an_event(make_client, ai):
    owner, _sid, b, pf, _project = _setup(make_client)
    _enable(owner, b)
    event_type = next(t for t in owner.get(f"{b}/project-types").json() if t["kind"] == "event")
    fake = ai(
        [
            call("lister_referentiels", {}),
            call(
                "proposer_projet_complet",
                {
                    "projet": {
                        "title": "Fête de fin d'année 2026",
                        "portfolio_id": pf["id"],
                        "project_type_id": event_type["id"],
                        "due_date": "2026-12-19",
                        "event": {
                            "venue": "Salle des fêtes",
                            "audience": "Équipe et partenaires",
                            "expected_attendance": 120,
                            "edition_label": "2026",
                        },
                    },
                    "taches": [{"title": "Réserver la salle", "due_date": "2026-11-25"}],
                },
                "t2",
            ),
            reply("Je vous propose la fête : validez-la."),
        ]
    )
    conv = owner.post(f"{b}/ai/conversations", json={"text": "Crée la fête"}).json()
    refs = fake.calls[1]["messages"][-1]["content"][0]["content"]
    assert '"nature": "event"' in refs
    action = owner.get(f"{b}/ai/conversations/{conv['id']}").json()["turns"][1]["actions"][0]
    event_line = next(c for c in action["changes"] if c["field"] == "Événement")
    assert event_line["after"] == (
        "lieu : Salle des fêtes · public : Équipe et partenaires · 120 participants attendus"
        " · édition 2026"
    )
    applied = owner.post(f"{b}/ai/actions/{action['id']}/apply").json()
    assert applied["state"] == "applied", applied
    project = owner.get(f"{b}/projects/{applied['project_id']}").json()
    assert project["event"]["venue"] == "Salle des fêtes"
    assert project["event"]["expected_attendance"] == 120
