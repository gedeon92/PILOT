"""Écrit le schéma OpenAPI sur la sortie standard, pour générer les types du frontend."""

import json

from pilot_api.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
