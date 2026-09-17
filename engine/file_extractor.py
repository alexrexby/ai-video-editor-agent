import re
from pathlib import Path

def extract_text_from_file(file_path: Path) -> str:
    """Extracts clean text from .docx, .pdf, .txt, .html, .md files."""
    suffix = file_path.suffix.lower()
    
    if suffix in [".txt", ".md"]:
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return f"Ошибка чтения текстового файла: {e}"
            
    elif suffix == ".docx":
        try:
            import docx
            doc = docx.Document(str(file_path))
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception as e:
            return f"Ошибка чтения docx: {e}"
            
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            return text.strip()
        except Exception as e:
            return f"Ошибка чтения pdf: {e}"
            
    elif suffix == ".html":
        try:
            raw_html = file_path.read_text(encoding="utf-8", errors="ignore")
            # Strip tags and clean BustaVoice html
            clean = re.sub(r'<[^>]+>', ' ', raw_html)
            clean = re.sub(r'\s+', ' ', clean).strip()
            return clean
        except Exception as e:
            return f"Ошибка чтения html: {e}"
            
    return ""
