
from pathlib import Path
from zipfile import BadZipFile, ZipFile

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

DOCX_REQUIRED_ENTRIES = {
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
}


def detect_file_type(file_path: str | Path) -> str:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    extension = path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: {extension}")

    if path.stat().st_size == 0:
        raise ValueError("Uploaded file is empty")

    with path.open("rb") as file:
        signature = file.read(8)

    if extension == ".pdf":
        if not signature.startswith(b"%PDF-"):
            raise ValueError("File extension does not match PDF content")

        return "pdf"

    if extension == ".docx":
        try:
            with ZipFile(path) as archive:
                entries = set(archive.namelist())

                if not DOCX_REQUIRED_ENTRIES.issubset(entries):
                    raise ValueError("Invalid DOCX package structure")

        except BadZipFile as exc:
            raise ValueError("DOCX file is not a valid ZIP package") from exc

        return "docx"

    if extension == ".txt":
        content = path.read_bytes()

        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                content.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    "TXT file must contain supported text encoding"
                ) from exc

        return "txt"

    raise ValueError("Unsupported file type")
