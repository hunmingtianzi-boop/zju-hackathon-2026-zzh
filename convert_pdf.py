import fitz
import os

input_dir = 'textbooks'
output_dir = '生医黑客松'

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

for filename in os.listdir(input_dir):
    if filename.endswith('.pdf'):
        pdf_path = os.path.join(input_dir, filename)
        md_filename = filename.replace('.pdf', '.md')
        md_path = os.path.join(output_dir, md_filename)
        
        print(f"Converting {filename} to {md_filename}...")
        
        doc = fitz.open(pdf_path)
        with open(md_path, 'w', encoding='utf-8') as md_file:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text()
                md_file.write(f"## Page {page_num + 1}\n\n")
                md_file.write(text)
                md_file.write("\n\n---\n\n")
        doc.close()

print("Conversion complete!")
