"""Envoi d'e-mails transactionnels par Brevo (décision D6).

Sans clé Brevo configurée, rien n'est envoyé : les alertes restent visibles dans l'application.
"""

import json
import urllib.error
import urllib.request

from pilot_api.config import get_settings

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class MailError(Exception):
    pass


def mail_configured() -> bool:
    settings = get_settings()
    return bool(settings.brevo_api_key and settings.mail_sender_email)


def send_email(*, to_email: str, to_name: str, subject: str, html: str, text: str) -> None:
    settings = get_settings()
    if not mail_configured():
        raise MailError("L'envoi d'e-mails n'est pas configuré (clé Brevo absente).")
    payload = {
        "sender": {"name": settings.mail_sender_name, "email": settings.mail_sender_email},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }
    request = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode(),
        headers={
            "api-key": settings.brevo_api_key or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status >= 300:
                raise MailError(f"Brevo a refusé l'envoi (HTTP {response.status}).")
    except urllib.error.HTTPError as error:
        # Corps d'erreur de Brevo non renvoyé : il peut citer la clé ou l'expéditeur.
        raise MailError(f"Brevo a refusé l'envoi (HTTP {error.code}).") from None
    except urllib.error.URLError:
        raise MailError("Brevo est injoignable pour le moment.") from None
