"""Lecture du texte des fichiers déposés (CDC §11).

Seul le texte déjà présent est lu : pas d'OCR. Un PDF scanné est signalé comme sans texte
plutôt que lu de façon fictive. Les limites évitent de bloquer le serveur :
5 Mo lus par fichier, 40 pages de PDF, environ 30 000 caractères.
"""

import csv
import io
import zipfile
from dataclasses import dataclass

from pilot_api.models import ExtractionStatus

MAX_READ_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 40
MAX_CHARS = 30_000
# Un fichier Office est une archive : on refuse celles qui gonflent démesurément une fois ouvertes.
MAX_UNZIPPED_BYTES = 60 * 1024 * 1024

TEXT_EXTENSIONS = {"txt", "md", "markdown", "text"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "heic", "bmp", "tif", "tiff"}


@dataclass
class Extracted:
    status: ExtractionStatus
    text: str = ""
    note: str | None = None


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _check_zip(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_UNZIPPED_BYTES:
            raise ValueError("archive trop volumineuse une fois ouverte")


def _rows_to_text(rows: list[list[str]]) -> str:
    """Un tableau devient du texte. Si sa première ligne contient une colonne « Projet »,
    chaque ligne devient « Projet — Colonne : valeur. … » pour être reconnue comme les messages."""
    rows = [[(c or "").strip() for c in row] for row in rows if any((c or "").strip() for c in row)]
    if not rows:
        return ""
    header = rows[0]
    lowered = [h.lower() for h in header]
    if "projet" in lowered or "project" in lowered:
        key = lowered.index("projet") if "projet" in lowered else lowered.index("project")
        lines = []
        for row in rows[1:]:
            if key >= len(row) or not row[key]:
                continue
            parts = [
                f"{header[i]} : {value}"
                for i, value in enumerate(row)
                if i != key and i < len(header) and header[i] and value
            ]
            lines.append(f"{row[key]} — " + ". ".join(parts) + ("." if parts else ""))
        return "\n".join(lines)
    return "\n".join(" ; ".join(c for c in row if c) for row in rows)


def _pdf(data: bytes) -> Extracted:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        return Extracted(ExtractionStatus.FAILED, note="PDF protégé par un mot de passe.")
    if len(reader.pages) > MAX_PDF_PAGES:
        return Extracted(
            ExtractionStatus.TOO_LONG,
            note=f"PDF de {len(reader.pages)} pages : {MAX_PDF_PAGES} pages au maximum. "
            "Déposez un extrait.",
        )
    return Extracted(ExtractionStatus.READ, "\n".join(p.extract_text() or "" for p in reader.pages))


def _docx(data: bytes) -> Extracted:
    from docx import Document

    _check_zip(data)
    document = Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        parts.append(_rows_to_text([[cell.text for cell in row.cells] for row in table.rows]))
    return Extracted(ExtractionStatus.READ, "\n".join(parts))


def _xlsx(data: bytes) -> Extracted:
    from openpyxl import load_workbook

    _check_zip(data)
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for sheet in workbook.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(["" if v is None else str(v) for v in row])
            if len(rows) > 2000:
                break
        parts.append(_rows_to_text(rows))
    workbook.close()
    return Extracted(ExtractionStatus.READ, "\n".join(parts))


def _pptx(data: bytes) -> Extracted:
    from pptx import Presentation

    _check_zip(data)
    presentation = Presentation(io.BytesIO(data))
    parts = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
                parts.append(_rows_to_text(rows))
    return Extracted(ExtractionStatus.READ, "\n".join(parts))


def _csv(data: bytes) -> Extracted:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return Extracted(
        ExtractionStatus.READ, _rows_to_text(list(csv.reader(io.StringIO(text), dialect)))
    )


READERS = {"pdf": _pdf, "docx": _docx, "xlsx": _xlsx, "pptx": _pptx, "csv": _csv}


def extract_text(filename: str, data: bytes) -> Extracted:
    ext = _extension(filename)
    if ext in IMAGE_EXTENSIONS:
        return Extracted(
            ExtractionStatus.UNSUPPORTED,
            note="Image conservée, mais pas lue : la reconnaissance de texte (OCR) "
            "n'est pas disponible.",
        )
    if ext not in READERS and ext not in TEXT_EXTENSIONS:
        return Extracted(
            ExtractionStatus.UNSUPPORTED,
            note="Format conservé mais non lu. Formats lus : PDF texte, Word (.docx), "
            "Excel (.xlsx), PowerPoint (.pptx), TXT, CSV, Markdown.",
        )
    if len(data) > MAX_READ_BYTES:
        return Extracted(
            ExtractionStatus.TOO_LARGE,
            note="Fichier conservé mais non lu : 5 Mo au maximum pour l'analyse.",
        )
    try:
        result = (
            READERS[ext](data)
            if ext in READERS
            else Extracted(ExtractionStatus.READ, _decode(data))
        )
    except Exception:  # fichier abîmé, mal nommé ou piégé : on le garde sans le lire
        return Extracted(
            ExtractionStatus.FAILED,
            note="Fichier conservé mais illisible (abîmé ou format différent de son extension).",
        )
    if result.status != ExtractionStatus.READ:
        return result
    text = result.text.replace("\x00", "").strip()
    if not text:
        note = (
            "Aucun texte lisible : ce PDF est probablement scanné. Sans reconnaissance de "
            "texte (OCR), il n'est pas analysé."
            if ext == "pdf"
            else "Aucun texte lisible dans ce fichier."
        )
        return Extracted(ExtractionStatus.EMPTY, note=note)
    if len(text) > MAX_CHARS:
        return Extracted(
            ExtractionStatus.TOO_LONG,
            note=f"Texte trop long ({len(text):,} caractères, {MAX_CHARS:,} au maximum) : "
            "déposez un extrait.".replace(",", " "),
        )
    return Extracted(ExtractionStatus.READ, text)
