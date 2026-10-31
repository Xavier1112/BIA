"""Run real-image smoke checks and make contact sheets for manual inspection.

No nuclear references are available here: this script does not measure accuracy.
"""
import json
import time
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
import tifffile
from nuclei.core import analyze_image, read_image, discover_images, AnalysisConfig
from nuclei.export import new_run, export_result, write_csv

ROOT=Path(__file__).resolve().parent

def main():
    paths=discover_images(ROOT/'data'/'breakhis_samples')
    if len(paths)<12: raise RuntimeError('Run fetch_samples.py or supply at least 12 real samples first.')
    run=new_run(ROOT/'results'/'real_smoke')
    rows=[]; panels=[]
    for path in paths:
        start=time.perf_counter(); image=read_image(path); result=analyze_image(image,AnalysisConfig())
        elapsed=time.perf_counter()-start
        folder=export_result(result,path,run)
        assert np.array_equal(tifffile.imread(folder/'labels.tiff'),result.labels)
        assert len(result.rows)==result.labels.max()
        rows.append(dict(file=str(path.relative_to(ROOT)),seconds=round(elapsed,4),
                         mean_hematoxylin=float(result.hematoxylin.mean()),**result.summary))
        # Side-by-side diagnostic thumbnails only; originals and masks remain full resolution.
        panel=Image.new('RGB',(1000,370),'white'); draw=ImageDraw.Draw(panel)
        draw.text((8,5),path.name,fill='black')
        draw.text((8,25),f"Candidates: {len(result.rows)} | coverage: {result.summary['coverage_percent']:.1f}% | no ground truth",fill='black')
        for x,data in [(0,image),(500,result.overlay())]:
            thumb=Image.fromarray(data); thumb.thumbnail((495,315)); panel.paste(thumb,(x,50))
        panels.append(panel)
        print(path.name,len(result.rows),f'{elapsed:.3f}s',flush=True)
    for page in range((len(panels)+3)//4):
        subset=panels[page*4:(page+1)*4]
        sheet=Image.new('RGB',(1000,370*len(subset)),'white')
        for i,panel in enumerate(subset): sheet.paste(panel,(0,370*i))
        sheet.save(run/f'contact_sheet_{page+1}.png')
    write_csv(run/'sample_checks.csv',rows)
    (run/'validation.json').write_text(json.dumps(dict(
        purpose='Software smoke check; no segmentation accuracy claim',
        config=vars(AnalysisConfig()),images=rows),indent=2),encoding='utf-8')
    print('OUTPUT',run)

if __name__=='__main__': main()
