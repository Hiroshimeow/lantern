import fitz
from pathlib import Path
src=Path(r"E:\git-project\lantern\.plan\lantern-markdown-main-20261018\test_turn1_markdown_artifacts\mermaid-seven-print.pdf")
out=src.parent/"pdf_pages_turn5"
out.mkdir(exist_ok=True)
with fitz.open(src) as doc:
    print("pages",len(doc))
    for i,p in enumerate(doc):
        pix=p.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
        dest=out/f"page-{i+1:02}.png"
        pix.save(dest)
        print(dest, dest.stat().st_size)
