import json, fitz
from pathlib import Path
pdf=Path(r"E:\git-project\lantern\.plan\lantern-markdown-main-20261018\test_turn1_markdown_artifacts\mermaid-seven-print.pdf")
out=pdf.parent/"test_turn6_gantt_crop.png"
with fitz.open(pdf) as doc:
    p=doc[4]
    spans=[]
    for block in p.get_text("dict")["blocks"]:
        for line in block.get("lines",[]):
            for span in line.get("spans",[]):
                t=span.get("text","").strip()
                if t:
                    spans.append({"text":t,"size":span["size"],"bbox":span["bbox"]})
    print(json.dumps(spans,indent=2))
    # Crop upper 22% of page containing Gantt; 4x for visual inspection.
    rect=p.rect
    clip=fitz.Rect(rect.x0,rect.y0,rect.x1,rect.y0+rect.height*0.24)
    pix=p.get_pixmap(matrix=fitz.Matrix(4,4),clip=clip,alpha=False)
    pix.save(out)
    print("crop",out,pix.width,pix.height)
