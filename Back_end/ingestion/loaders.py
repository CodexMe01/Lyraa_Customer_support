import os
import base64
import io
import sys
import time
from llama_index.core import SimpleDirectoryReader, Document, VectorStoreIndex, Settings
from tavily import TavilyClient
import fitz
import pytesseract
from PIL import Image

# How many hours back to look when mode='recent'
RECENT_FILES_LOOKBACK_HOURS = 24


def load_local_documents(input_dir: str, mode: str = "all"):
    """Load documents from a local directory, identifying file types and applying OCR where appropriate.
    
    Args:
        input_dir: Path to the directory to scan.
        mode: 'all' to process every file, or 'recent' to process only files
              modified within the last RECENT_FILES_LOOKBACK_HOURS hours.
    """
    if not os.path.exists(input_dir):
        os.makedirs(input_dir)
        print(f"Created directory {input_dir}. Please add documents here.")
        return []

    # Determine the earliest modification time we care about (for 'recent' mode)
    cutoff_time = None
    if mode == "recent":
        cutoff_time = time.time() - (RECENT_FILES_LOOKBACK_HOURS * 3600)
        print(f"[Recent mode] Only processing files modified in the last {RECENT_FILES_LOOKBACK_HOURS} hours.")
        
    documents = []
    for filename in os.listdir(input_dir):
        file_path = os.path.join(input_dir, filename)
        if not os.path.isfile(file_path):
            continue

        # Skip files that are older than the cutoff when in 'recent' mode
        if cutoff_time is not None:
            file_mtime = os.path.getmtime(file_path)
            if file_mtime < cutoff_time:
                print(f"  Skipping {filename} (not modified in the last {RECENT_FILES_LOOKBACK_HOURS}h).")
                continue
            
        ext = os.path.splitext(filename)[1].lower()
        print(f"Processing file: {filename} (extension: {ext})")
        
        try:
            if ext == ".pdf":
                print(f"  Routing {filename} to PDF OCR reader...")
                pdf_docs = load_pdf_with_ocr(file_path, "document", filename)
                documents.extend(pdf_docs)
            elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff"]:
                print(f"  Routing {filename} to Image OCR reader...")
                img_docs = load_image_with_ocr(file_path, filename)
                documents.extend(img_docs)
            else:
                print(f"  Routing {filename} to standard SimpleDirectoryReader...")
                reader = SimpleDirectoryReader(input_files=[file_path])
                docs = reader.load_data()
                # Set consistent metadata
                for doc in docs:
                    if not doc.metadata:
                        doc.metadata = {}
                    doc.metadata["source_file"] = filename
                    doc.metadata["doc_category"] = "standard_document"
                documents.extend(docs)
        except Exception as e:
            print(f"Error loading file {filename}: {e}")
            
    print(f"Loaded a total of {len(documents)} document pages/sections.")
    return documents

def load_website_data(urls: list):
    """Load website data using Tavily Extract API."""
    if not urls:
        return []
        
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        raise ValueError("TAVILY_API_KEY environment variable is not set. Please set it in .env.")
        
    client = TavilyClient(api_key=tavily_api_key)
    response = client.extract(urls=urls, extract_depth="advanced")
    
    documents = []
    for result in response.get("results", []):
        url = result.get("url")
        content = result.get("raw_content", "")
        if content:
            documents.append(Document(
                text=content,
                metadata={
                    "source_url": url,
                    "doc_category": "website"
                }
            ))
    return documents

def load_pdf_with_ocr(file_path: str, category: str, source_name: str) -> list[Document]:
    """
    Load a PDF and extract text page by page.
    Falls back to OCR (pytesseract) for scanned/image-only pages.
    """
    docs = []
    try:
        pdf = fitz.open(file_path)
    except Exception as e:
        print(f"Error opening PDF {file_path}: {e}")
        return []

    for page_num in range(len(pdf)):
        page = pdf[page_num]
        text = page.get_text("text").strip()

        if not text:  # scanned page — use OCR
            try:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img)
            except Exception as ocr_err:
                print(f"    Warning: OCR failed on page {page_num + 1} of {source_name}: {ocr_err}")
                text = ""

        if text.strip():
            docs.append(Document(
                text=text,
                metadata={
                    "source_file": source_name,
                    "doc_category": category,
                    "page": page_num + 1,
                }
            ))

    pdf.close()
    print(f"  ✓ {source_name} — {len(docs)} pages loaded")
    return docs

def load_image_with_ocr(file_path: str, filename: str) -> list[Document]:
    """Extract text from an image using pytesseract OCR."""
    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)
        if text.strip():
            return [Document(
                text=text,
                metadata={
                    "source_file": filename,
                    "doc_category": "image_ocr"
                }
            )]
    except Exception as e:
        print(f"Error OCR-ing image {filename}: {e}")
    return []
