import re
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid5
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PageObject, PdfReader
from pypdf.errors import PdfReadError

from app.domain import DocumentType, ExtractedBlock, ExtractedDocument

READER_VERSION = "cv-reader-v2"
MIN_READABLE_CHARACTERS = 40
MAX_DOCX_ENTRIES = 2_000


class DocumentReadError(ValueError):
    """A safe, user-facing document-reading error."""


def validate_upload_bytes(
    *, filename: str, content: bytes, max_docx_uncompressed_bytes: int
) -> DocumentType:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise DocumentReadError("That file does not appear to be a valid PDF")
        return DocumentType.PDF
    if suffix == ".docx":
        _validate_docx_archive(BytesIO(content), max_docx_uncompressed_bytes)
        return DocumentType.DOCX
    raise DocumentReadError("Upload a PDF or DOCX file")


def read_document(
    path: Path,
    *,
    resume_id: UUID,
    max_pages: int,
    max_docx_uncompressed_bytes: int,
) -> ExtractedDocument:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path, resume_id=resume_id, max_pages=max_pages)
    if suffix == ".docx":
        return _read_docx(
            path,
            resume_id=resume_id,
            max_docx_uncompressed_bytes=max_docx_uncompressed_bytes,
        )
    raise DocumentReadError("Upload a PDF or DOCX file")


def _read_pdf(path: Path, *, resume_id: UUID, max_pages: int) -> ExtractedDocument:
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            raise DocumentReadError("Password-protected PDFs are not supported")
        page_count = len(reader.pages)
        if page_count == 0:
            raise DocumentReadError("The PDF has no pages")
        if page_count > max_pages:
            raise DocumentReadError(f"The PDF has more than the {max_pages}-page limit")

        blocks: list[ExtractedBlock] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = _extract_pdf_page_text(page)
            if not text:
                continue
            blocks.append(
                _block(
                    resume_id=resume_id,
                    ordinal=len(blocks) + 1,
                    source_label=f"Page {page_number}",
                    page_number=page_number,
                    kind="page",
                    text=text,
                )
            )
    except DocumentReadError:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        raise DocumentReadError("The PDF is damaged or cannot be read") from exc

    return _build_document(
        resume_id=resume_id,
        document_type=DocumentType.PDF,
        page_count=page_count,
        blocks=blocks,
    )


def _extract_pdf_page_text(page: PageObject) -> str:
    layout_text = _normalise_text(page.extract_text(extraction_mode="layout") or "")
    plain_text = _normalise_text(page.extract_text() or "")

    if _readable_character_count(plain_text) > _readable_character_count(layout_text):
        return plain_text
    return layout_text


def _readable_character_count(value: str) -> int:
    return sum(not character.isspace() for character in value)


def _read_docx(
    path: Path, *, resume_id: UUID, max_docx_uncompressed_bytes: int
) -> ExtractedDocument:
    try:
        _validate_docx_archive(path, max_docx_uncompressed_bytes)
        document = Document(path)
        blocks: list[ExtractedBlock] = []
        table_number = 0
        paragraph_number = 0
        for item in _iter_docx_blocks(document):
            if isinstance(item, Paragraph):
                paragraph_number += 1
                text = _normalise_text(item.text)
                label = f"Paragraph {paragraph_number}"
                kind = "paragraph"
            else:
                table_number += 1
                text = _normalise_text(_table_text(item))
                label = f"Table {table_number}"
                kind = "table"
            if not text:
                continue
            blocks.append(
                _block(
                    resume_id=resume_id,
                    ordinal=len(blocks) + 1,
                    source_label=label,
                    page_number=None,
                    kind=kind,
                    text=text,
                )
            )
    except DocumentReadError:
        raise
    except (BadZipFile, KeyError, OSError, ValueError) as exc:
        raise DocumentReadError("The DOCX file is damaged or cannot be read") from exc

    return _build_document(
        resume_id=resume_id,
        document_type=DocumentType.DOCX,
        page_count=None,
        blocks=blocks,
    )


def _validate_docx_archive(source: Path | BytesIO, max_uncompressed_bytes: int) -> None:
    try:
        with ZipFile(source) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise DocumentReadError("That file does not appear to be a valid DOCX")
            if len(entries) > MAX_DOCX_ENTRIES:
                raise DocumentReadError("The DOCX contains too many internal files")
            if sum(entry.file_size for entry in entries) > max_uncompressed_bytes:
                raise DocumentReadError("The DOCX expands beyond the safe processing limit")
    except BadZipFile as exc:
        raise DocumentReadError("That file does not appear to be a valid DOCX") from exc


def _iter_docx_blocks(document: DocumentObject) -> Iterator[Paragraph | Table]:
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _table_text(table: Table) -> str:
    rows: list[str] = []
    for row in table.rows:
        values = [_normalise_text(cell.text) for cell in row.cells]
        if any(values):
            rows.append(" | ".join(values))
    return "\n".join(rows)


def _normalise_text(value: str) -> str:
    lines: list[str] = []
    previous_blank = False
    for raw_line in value.replace("\x00", "").replace("\r\n", "\n").split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if line:
            lines.append(line)
            previous_blank = False
        elif lines and not previous_blank:
            lines.append("")
            previous_blank = True
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _block(
    *,
    resume_id: UUID,
    ordinal: int,
    source_label: str,
    page_number: int | None,
    kind: str,
    text: str,
) -> ExtractedBlock:
    return ExtractedBlock(
        block_id=uuid5(resume_id, f"{READER_VERSION}:{kind}:{ordinal}"),
        ordinal=ordinal,
        source_label=source_label,
        page_number=page_number,
        kind=kind,
        text=text,
    )


def _build_document(
    *,
    resume_id: UUID,
    document_type: DocumentType,
    page_count: int | None,
    blocks: list[ExtractedBlock],
) -> ExtractedDocument:
    char_count = sum(len(block.text) for block in blocks)
    if char_count < MIN_READABLE_CHARACTERS:
        raise DocumentReadError(
            "We could not find enough readable text. Scanned CVs are not supported yet"
        )
    return ExtractedDocument(
        reader_version=READER_VERSION,
        resume_id=resume_id,
        document_type=document_type,
        page_count=page_count,
        char_count=char_count,
        blocks=blocks,
    )
