import os
import re

def chunk_markdown(file_path, output_base_dir):
    book_name = os.path.basename(file_path).replace('.md', '')
    book_dir = os.path.join(output_base_dir, book_name)
    if not os.path.exists(book_dir):
        os.makedirs(book_dir)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    current_chapter = "00_绪论"
    current_section = "00_开篇"
    chunk_content = []
    
    for line in lines:
        # Detect Chapter (Level 1)
        ch_match = re.match(r'^#\s+(第[一二三四五六七八九十]+章|绪论|前言|目录|附录)(.*)', line)
        # Detect Section (Level 2)
        sec_match = re.match(r'^#+\s+(第[一二三四五六七八九十]+节)(.*)', line)
        
        if ch_match:
            # Save previous chunk
            save_chunk(book_dir, current_chapter, current_section, chunk_content)
            current_chapter = ch_match.group(1).strip() + ch_match.group(2).strip()
            current_chapter = re.sub(r'[\\/:*?"<>|]', '_', current_chapter) # Sanitize
            current_section = "00_概要"
            chunk_content = [line]
        elif sec_match:
            # Save previous chunk
            save_chunk(book_dir, current_chapter, current_section, chunk_content)
            current_section = sec_match.group(1).strip() + sec_match.group(2).strip()
            current_section = re.sub(r'[\\/:*?"<>|]', '_', current_section) # Sanitize
            chunk_content = [line]
        else:
            chunk_content.append(line)
            
    # Save last chunk
    save_chunk(book_dir, current_chapter, current_section, chunk_content)

def save_chunk(book_dir, chapter, section, content):
    if not content or len("".join(content).strip()) < 10:
        return
    
    # Sanitize filename: keep only Chinese, Alphanumeric, and underscores
    safe_chapter = re.sub(r'[^\w\u4e00-\u9fa5]', '_', chapter)
    safe_section = re.sub(r'[^\w\u4e00-\u9fa5]', '_', section)
    # Limit length to avoid Windows MAX_PATH issues
    filename = f"{safe_chapter[:50]}_{safe_section[:50]}.md"
    file_path = os.path.join(book_dir, filename)
    
    # If file exists, append (shouldn't happen with unique names but good for safety)
    mode = 'w'
    with open(file_path, mode, encoding='utf-8') as f:
        f.writelines(content)

def main():
    input_dir = '生医黑客松'
    output_dir = '生医黑客松/chunks'
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    md_files = [f for f in os.listdir(input_dir) if f.endswith('.md') and not f.startswith('chunks')]
    for md_file in sorted(md_files):
        print(f"Chunking: {md_file}...")
        chunk_markdown(os.path.join(input_dir, md_file), output_dir)

if __name__ == "__main__":
    main()
