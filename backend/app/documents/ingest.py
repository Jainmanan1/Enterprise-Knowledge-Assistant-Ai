import io
import os

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
)


def extract_text(filename: str, content: bytes) -> str:
    ext = os.path.splitext(filename.lower())[1]


    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    return content.decode("utf-8", errors="ignore")


def chunk_text(text: str) -> list[str]:
    return [
        chunk
        for chunk in _splitter.split_text(text)
        if chunk.strip()
    ]


