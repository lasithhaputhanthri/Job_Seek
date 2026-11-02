import sys
from pypdf import PdfReader

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

reader = PdfReader("data/cv.pdf")
text = "\n".join([page.extract_text() or "" for page in reader.pages])
print(f"Total pages: {len(reader.pages)}")
print(f"Total characters extracted: {len(text)}")
print("--- PREVIEW OF EXTRACTED CV TEXT ---")
# Replace fancy ligatures for safe console printing if needed
safe_text = text.encode('ascii', errors='replace').decode('ascii')
print(safe_text[:1200])
