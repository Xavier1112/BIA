"""Download 12 public BreaKHis images from an explicitly documented course-data mirror.

No authentication is used. This is a development sample, not a random validation set.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from PIL import Image

REPO='PerceptiLabs/breakhis-400x'
COMMIT='dcaa73071e8f4facce22a56d45319bf3a4b62d45'
ROOT=Path(__file__).resolve().parent/'data'/'breakhis_samples'

def get(url):
    with urlopen(Request(url,headers={'User-Agent':'BreaKHis-Nuclei-Explorer-demo'}),timeout=45) as r:
        return r.read(10_000_000)

def main():
    tree=json.loads(get(f'https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1'))['tree']
    selected=[]
    for diagnosis in ['benign','malignant']:
        paths=sorted(t['path'] for t in tree if f'/{diagnosis}/' in t['path'] and t['path'].endswith('.png'))
        # Round-robin tumor subtypes and avoid repeated specimen prefixes where possible.
        groups={}
        for path in paths:
            subtype=Path(path).name.split('-')[0]
            groups.setdefault(subtype,[]).append(path)
        seen=set(); chosen=[]
        while len(chosen)<6:
            progress=False
            for subtype in sorted(groups):
                while groups[subtype]:
                    path=groups[subtype].pop(0)
                    specimen=Path(path).stem.rsplit('-',2)[0]
                    if specimen in seen: continue
                    seen.add(specimen); chosen.append(path); progress=True; break
                if len(chosen)==6: break
            if not progress: raise RuntimeError('Insufficient distinct specimens in mirror.')
        selected.extend((diagnosis,p) for p in chosen)
    ROOT.mkdir(parents=True,exist_ok=True)
    def download(item):
        diagnosis,path=item
        url=f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/{quote(path)}'
        target=ROOT/diagnosis/Path(path).name; target.parent.mkdir(exist_ok=True)
        if not target.exists():
            payload=get(url)
            if not payload.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('Download is not PNG')
            with target.open('xb') as f: f.write(payload)
        with Image.open(target) as im: im.verify()
        print(target.name,flush=True)
        return dict(file=str(target.relative_to(ROOT)),diagnosis=diagnosis,source_url=url,
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    with ThreadPoolExecutor(max_workers=4) as pool: records=list(pool.map(download,selected))
    (ROOT/'manifest.json').write_text(json.dumps(dict(
        course_source='https://www.kaggle.com/forderation/breakhis-400x',
        mirror=f'https://github.com/{REPO}',mirror_commit=COMMIT,
        note='Mirror README credits the course Kaggle dataset. Not independently byte-matched to Kaggle. '
             'Purposeful 6 benign / 6 malignant development sample across subtypes; not an accuracy test set.',
        images=records),indent=2),encoding='utf-8')

if __name__=='__main__': main()
