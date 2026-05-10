import fitz
import os
import re
from collections import Counter

def clean_text(text):
    # Remove backspaces and replacement characters
    text = text.replace('\x08', '').replace('\ufffd', '')
    # Remove excessive dots
    text = re.sub(r'\.{4,}', '...', text)
    return text.strip()

def process_pdf(pdf_path, output_path):
    print(f"Processing: {os.path.basename(pdf_path)}...")
    doc = fitz.open(pdf_path)
    
    # First pass: Analyze font sizes to find heading patterns
    font_sizes = []
    for page in doc[:20]: # Check first 20 pages for stats
        dict_data = page.get_text("dict")
        for block in dict_data.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_sizes.append(round(span["size"], 1))
    
    if not font_sizes:
        print(f"Warning: Could not extract font info from {pdf_path}")
        return

    size_counts = Counter(font_sizes)
    common_size = size_counts.most_common(1)[0][0]
    # Headings are usually larger than body text
    heading_sizes = sorted([size for size in size_counts if size > common_size], reverse=True)
    
    print(f"  Detected common font size: {common_size}")
    
    md_content = []
    current_chapter = ""
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        dict_data = page.get_text("dict")
        page_width = page.rect.width
        page_height = page.rect.height
        
        # Sort blocks by vertical then horizontal position
        blocks = dict_data.get("blocks", [])
        blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
        
        page_text = ""
        for block in blocks:
            if block["type"] != 0: continue # Skip images
            
            block_lines = []
            is_heading = False
            h_level = 0
            
            for line in block["lines"]:
                line_text = ""
                for span in line["spans"]:
                    text = span["text"]
                    size = round(span["size"], 1)
                    
                    # Detect heading level based on size
                    if size > common_size + 1:
                        is_heading = True
                        if size >= heading_sizes[0] if heading_sizes else size:
                            h_level = 1
                        elif size >= (heading_sizes[1] if len(heading_sizes) > 1 else size):
                            h_level = 2
                        else:
                            h_level = 3
                    
                    line_text += text
                
                if line_text.strip():
                    block_lines.append(line_text.strip())
            
            full_block_text = " ".join(block_lines)
            full_block_text = clean_text(full_block_text)
            
            if not full_block_text: continue
            
            # Additional Regex check for headings (e.g., "第一章", "第一节")
            if re.match(r'^(第[一二三四五六七八九十]+[章节])|绪论|前言', full_block_text):
                h_level = 1
                is_heading = True
            elif re.match(r'^第[一二三四五六七八九十]+节', full_block_text):
                h_level = 2
                is_heading = True
            elif re.match(r'^[一二三四五六七八九十]、', full_block_text):
                h_level = 3
                is_heading = True
            elif "临床病例分析" in full_block_text or "病例" in full_block_text:
                full_block_text = f"### 💡 {full_block_text}"
                is_heading = True
                h_level = 0 # Handled specially
            
            if is_heading and h_level > 0:
                prefix = "#" * h_level
                md_content.append(f"\n{prefix} {full_block_text}\n")
            elif h_level == 0 and "💡" in full_block_text:
                md_content.append(f"\n{full_block_text}\n")
            else:
                # Filter out headers/footers (usually single lines at extreme top/bottom)
                bbox = block["bbox"]
                if bbox[1] < 50 or bbox[3] > page_height - 50:
                    # Likely header or footer
                    if len(full_block_text) < 20: continue
                
                md_content.append(full_block_text)

    # Combine and save
    final_text = "\n".join(md_content)
    # Post-process: clean up multiple newlines
    final_text = re.sub(r'\n{3,}', '\n\n', final_text)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_text)
    
    doc.close()
    print(f"  Finished: {output_path}")

def main():
    input_dir = 'textbooks'
    output_dir = '生医黑客松'
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    pdf_files = [f for f in os.listdir(input_dir) if f.endswith('.pdf')]
    for pdf_file in sorted(pdf_files):
        pdf_path = os.path.join(input_dir, pdf_file)
        md_file = pdf_file.replace('.pdf', '.md')
        output_path = os.path.join(output_dir, md_file)
        process_pdf(pdf_path, output_path)

if __name__ == "__main__":
    main()
