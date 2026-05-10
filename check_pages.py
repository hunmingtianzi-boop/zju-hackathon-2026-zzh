import fitz
import os

input_dir = 'textbooks'
for filename in sorted(os.listdir(input_dir)):
    if filename.endswith('.pdf'):
        pdf_path = os.path.join(input_dir, filename)
        doc = fitz.open(pdf_path)
        print(f"{filename}: {doc.page_count} pages")
        doc.close()
