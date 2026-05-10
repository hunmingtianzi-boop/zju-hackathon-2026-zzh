import fitz
import os
import re

input_file = 'textbooks/01_局部解剖学.pdf'
output_file = '生医黑客松/01_局部解剖学.md'

print(f"Refining conversion for {input_file}...")

doc = fitz.open(input_file)
with open(output_file, 'w', encoding='utf-8') as md_file:
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        # Use blocks to better handle multi-column text
        blocks = page.get_text("blocks")
        
        md_file.write(f"## Page {page_num + 1}\n\n")
        
        # Sort blocks by vertical then horizontal position
        blocks.sort(key=lambda b: (b[1], b[0]))
        
        page_text = ""
        for b in blocks:
            block_text = b[4]
            # Clean up garbage characters
            block_text = block_text.replace('\x08', '') # Backspace
            block_text = block_text.replace('\ufffd', '') # Replacement char
            
            # Remove repeated dots (often used in TOC)
            block_text = re.sub(r'\.{3,}', '...', block_text)
            
            page_text += block_text + "\n"
        
        if not page_text.strip():
            md_file.write("> [Warning: No text detected on this page. It might be an image or requires OCR.]\n\n")
        else:
            md_file.write(page_text)
            
        md_file.write("\n\n---\n\n")

doc.close()
print("Refinement complete!")
