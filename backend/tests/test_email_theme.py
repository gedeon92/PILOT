from pilot_api.email_theme import render_email


def test_email_escapes_texts_and_keeps_the_link():
    page = render_email(
        kicker="Invitation",
        title="<script>alert(1)</script> vous invite",
        paragraphs=["Bonjour <b>toi</b>"],
        button_label="Rejoindre",
        button_url="https://pilot.example/invitation/abc?x=1&y=2",
        footer="Pied",
    )

    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "&lt;b&gt;toi&lt;/b&gt;" in page
    assert "https://pilot.example/invitation/abc?x=1&amp;y=2" in page
    # Les polices sont entre guillemets doubles : l'attribut style n'est pas coupé.
    assert 'font-family:"Segoe UI"' in page
