# Text extraction from files, URL, and Anki export.

import csv
import html
import os
import re
import sqlite3
import tempfile
from io import StringIO
from typing import Any

import pandas as pd
import requests

import constants
from errors import ErrorHandler
from resources import get_file_parsers
from utils import detect_file_encoding

logger = __import__("logging").getLogger(__name__)


def clean_anki_field(text: str) -> str:
    """Helper to clean a single Anki field content."""
    text = re.sub(r'\{\{c\d+::(.*?)(?::.*?)?\}\}', r'\1', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\[sound:.*?\]', '', text)
    text = re.sub(r'\[Image:.*?\]', '', text)
    return text.strip()


def parse_anki_txt_export(uploaded_file: Any) -> str:
    """Robustly parse Anki export txt files."""
    try:
        bytes_data = uploaded_file.getvalue()
        encoding = detect_file_encoding(bytes_data)
        content = bytes_data.decode(encoding, errors='ignore')

        extracted_words = []
        f_io = StringIO(content)
        reader = csv.reader(f_io, delimiter='\t')

        for row in reader:
            if not row:
                continue
            if row[0].startswith('#'):
                continue

            target_text = ""
            if len(row) > 1 and (re.match(r'^\[sound:.*\]$', row[0].strip()) or row[0].strip().isdigit()):
                target_text = row[1]
            else:
                target_text = row[0]

            clean_text = clean_anki_field(target_text)
            clean_word = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$', '', clean_text)
            if clean_word and len(clean_word) >= 2:
                extracted_words.append(clean_word)

        return "\n".join(extracted_words)

    except Exception as e:
        return ErrorHandler.handle_file_error(e, "Anki Export Import")


def extract_text_from_url(url: str) -> str:
    """Extract text content from a URL."""
    _, _, _, _, BeautifulSoup = get_file_parsers()

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=constants.REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        for element in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
            element.decompose()

        return soup.get_text(separator=' ', strip=True)
    except requests.RequestException as e:
        return ErrorHandler.handle_file_error(e, "URL")
    except Exception as e:
        return ErrorHandler.handle_file_error(e, "URL parsing")


def extract_from_txt(uploaded_file: Any) -> str:
    """Extract text from TXT file."""
    bytes_data = uploaded_file.getvalue()
    encoding = detect_file_encoding(bytes_data)

    try:
        return bytes_data.decode(encoding)
    except UnicodeDecodeError:
        logger.warning("Decode failed with %s, trying latin-1", encoding)
        return bytes_data.decode('latin-1', errors='ignore')


def extract_from_pdf(uploaded_file: Any) -> str:
    """Extract text from PDF file."""
    pypdf, _, _, _, _ = get_file_parsers()

    try:
        reader = pypdf.PdfReader(uploaded_file)
        pages_text = [page.extract_text() for page in reader.pages if page.extract_text()]
        return "\n".join(pages_text)
    except Exception as e:
        return ErrorHandler.handle_file_error(e, "PDF")


def extract_from_docx(uploaded_file: Any) -> str:
    """Extract text from DOCX file."""
    _, docx, _, _, _ = get_file_parsers()

    try:
        doc = docx.Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception as e:
        return ErrorHandler.handle_file_error(e, "DOCX")


def extract_from_epub(uploaded_file: Any) -> str:
    """Extract text from EPUB file."""
    _, _, ebooklib, epub, BeautifulSoup = get_file_parsers()

    try:
        book = epub.read_epub(uploaded_file)
        text_parts = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text_parts.append(soup.get_text(separator=' ', strip=True))
        return "\n".join(text_parts)
    except Exception as e:
        return ErrorHandler.handle_file_error(e, "EPUB")


def extract_from_csv(uploaded_file: Any) -> str:
    """Extract text from CSV file."""
    bytes_data = uploaded_file.getvalue()
    encoding = detect_file_encoding(bytes_data)

    try:
        content = bytes_data.decode(encoding)
        df = pd.read_csv(StringIO(content))
        text_parts = []
        for col in df.columns:
            col_text = df[col].astype(str)
            col_text = col_text[col_text.notna() & (col_text != '') & (col_text != 'nan')]
            text_parts.extend(col_text.tolist())
        return " ".join(text_parts)
    except Exception as e:
        return ErrorHandler.handle_file_error(e, "CSV")


def extract_from_excel(uploaded_file: Any) -> str:
    """Extract text from Excel file."""
    try:
        df = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
    except Exception:
        try:
            df = pd.read_excel(uploaded_file, sheet_name=None, engine='xlrd')
        except Exception as e:
            return ErrorHandler.handle_file_error(e, "Excel")

    try:
        text_parts = []
        for sheet_name, sheet_df in df.items():
            for col in sheet_df.columns:
                col_text = sheet_df[col].astype(str)
                col_text = col_text[col_text.notna() & (col_text != '') & (col_text != 'nan')]
                text_parts.extend(col_text.tolist())
        return " ".join(text_parts)
    except Exception as e:
        return ErrorHandler.handle_file_error(e, "Excel")


def extract_from_sqlite(uploaded_file: Any) -> str:
    """Extract text from SQLite database file."""
    tmp_db_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_db:
            tmp_db.write(uploaded_file.getvalue())
            tmp_db_path = tmp_db.name

        with sqlite3.connect(tmp_db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT stem FROM WORDS WHERE stem IS NOT NULL")
                rows = cursor.fetchall()
                text = " ".join([row[0] for row in rows if row[0]])

                if not text:
                    cursor.execute("SELECT word FROM WORDS")
                    rows = cursor.fetchall()
                    text = " ".join([row[0] for row in rows if row[0]])

                return text
            except sqlite3.OperationalError as e:
                return f"Error reading DB schema: {e}"

    except Exception as e:
        return ErrorHandler.handle_file_error(e, "SQLite DB")
    finally:
        if tmp_db_path and os.path.exists(tmp_db_path):
            try:
                os.remove(tmp_db_path)
            except OSError as e:
                logger.warning("Could not remove temp DB: %s", e)


def extract_text_from_file(uploaded_file: Any) -> str:
    """Main function to extract text from uploaded files."""
    file_type = uploaded_file.name.split('.')[-1].lower()

    extractors = {
        'txt': extract_from_txt,
        'pdf': extract_from_pdf,
        'docx': extract_from_docx,
        'epub': extract_from_epub,
        'db': extract_from_sqlite,
        'sqlite': extract_from_sqlite,
        'csv': extract_from_csv,
        'xlsx': extract_from_excel,
        'xls': extract_from_excel,
    }

    extractor = extractors.get(file_type)
    if extractor:
        return extractor(uploaded_file)

    return f"Unsupported file type: {file_type}"


def is_upload_too_large(uploaded_file: Any) -> bool:
    """Check if uploaded file exceeds size limit."""
    if not uploaded_file:
        return False
    size = getattr(uploaded_file, "size", None)
    if size is None:
        return False
    return size > constants.MAX_UPLOAD_BYTES
