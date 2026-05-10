import fitz
import json

doc = fitz.open('textbooks/01_局部解剖学.pdf')
page = doc[30] # Page 31
text_dict = page.get_text("dict")
print(json.dumps(text_dict, indent=2, ensure_ascii=False)[:2000])
doc.close()
