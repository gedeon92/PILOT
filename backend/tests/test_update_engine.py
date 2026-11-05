"""Garde-fous du moteur de reconnaissance (CDC §10), sans base de données."""

import uuid

from pilot_api.updates.engine import MemberInfo, ProjectInfo, TextSource, analyse, read_date


def _run(text, *titles, filename=None, members=()):
    projects = [ProjectInfo(uuid.uuid4(), t) for t in titles]
    names = {p.id: p.title for p in projects}
    result = analyse([TextSource(filename or "Message", text, filename)], projects, list(members))
    drafts = [
        (names.get(d.target_id), {c.field: c.display for c in d.changes}) for d in result.drafts
    ]
    return drafts, result.notes


def test_future_or_negated_completion_never_sets_done():
    for text in ("Atlas — Statut : sera terminé demain", "Atlas — Statut : n'est pas terminé"):
        drafts, notes = _run(text, "Atlas")
        assert drafts == []
        assert "le statut n'est pas modifié" in notes[0]


def test_done_is_never_proposed_even_when_explicit():
    drafts, notes = _run("Atlas — Statut : terminé", "Atlas")
    assert drafts == []
    assert "bilan" in notes[0]


def test_next_step_citing_another_project_keeps_its_project():
    drafts, _ = _run("Atlas — Prochaine étape : attendre la livraison d'Orion", "Atlas", "Orion")
    assert drafts == [("Atlas", {"next_step": "attendre la livraison d'Orion"})]


def test_contradictory_values_are_set_aside():
    drafts, _ = _run("Atlas — Statut : en cours. Statut : bloqué. Avancement : 20 %", "Atlas")
    assert drafts == [("Atlas", {"progress": "20 %"})]
    _, notes = _run("Atlas — Statut : en cours. Statut : bloqué", "Atlas")
    assert "Deux valeurs différentes pour Statut" in notes[0]


def test_relative_dates_are_not_converted():
    day, issue = read_date("vendredi prochain")
    assert day is None and "relative" in issue
    day, issue = read_date("20 novembre")
    assert day is None and "Année manquante" in issue
    assert read_date("20 nov. 2026")[0].isoformat() == "2026-11-20"
    assert read_date("2026-11-20")[0].isoformat() == "2026-11-20"
    assert read_date("20/11/26")[0].isoformat() == "2026-11-20"


def test_a_sentence_mentioning_a_project_is_not_a_target():
    drafts, notes = _run("Orion doit d'abord livrer.", "Orion")
    assert drafts == []


def test_accents_word_order_and_acronyms():
    drafts, _ = _run(
        "SALON INTERNATIONAL AGRICULTURE : Avancement : 50 %",
        "Salon de l'agriculture internationale",
    )
    # Mots en partie différents : projet à préciser, jamais choisi d'office.
    assert drafts == [(None, {"progress": "50 %"})]
    drafts, _ = _run("Barometre — Avancement : 50 %", "Baromètre")
    assert drafts == [("Baromètre", {"progress": "50 %"})]
    drafts, _ = _run("SIA — Avancement : 50 %", "Salon International Agriculture")
    assert drafts == [("Salon International Agriculture", {"progress": "50 %"})]


def test_more_specific_title_wins():
    drafts, _ = _run("Atlas Maroc — Avancement : 50 %", "Atlas", "Atlas Maroc")
    assert drafts == [("Atlas Maroc", {"progress": "50 %"})]


def test_file_name_designates_the_project():
    drafts, _ = _run("Avancement : 70 %", "barometre", filename="CR_barometre_nov.docx")
    assert drafts == [("barometre", {"progress": "70 %"})]


def test_owner_is_matched_to_a_member_or_kept_as_a_name():
    marie = MemberInfo(uuid.uuid4(), "Marie Diallo", "marie@exemple.com")
    drafts, _ = _run("Atlas — Responsable : Marie", "Atlas", members=[marie])
    assert drafts == [("Atlas", {"owner": "Marie Diallo"})]
    drafts, _ = _run("Atlas — Responsable : Mon assistante", "Atlas", members=[marie])
    assert drafts == [("Atlas", {"owner": "Mon assistante (sans compte)"})]
