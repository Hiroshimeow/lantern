"""Python renderer-only baseline; NOT a Milkdown/browser comparison."""
from __future__ import annotations
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import plugin
from renderer_benchmark import SIZES, make_document

def run():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)
        output=[]
        for size in SIZES:
            file=path/f'{size}.md';file.write_text(make_document(size),encoding='utf8')
            samples=[];html_size=None;truncated=False
            for _ in range(10):
                begin=time.perf_counter()
                _,html=plugin._render_markdown(file,path)
                samples.append((time.perf_counter()-begin)*1000)
                html_size=len(html.encode('utf8'))
                truncated='Preview truncated to keep' in html
            output.append({'sourceBytes':file.stat().st_size,'htmlBytes':html_size,
                'serverRenderMedianMs':round(statistics.median(samples),2),
                'serverRenderP95ApproxMs':round(sorted(samples)[-1],2),
                'truncated':truncated})
        print(json.dumps({'kind':'PYTHON_ONLY_BASELINE','notBrowserLatency':True,
                          'notMilkdownMeasurement':True,'sizes':output},indent=2))
if __name__=='__main__':run()
