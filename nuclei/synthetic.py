"""Deterministic synthetic H&E-like objects. These are NOT clinical images."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from skimage.draw import ellipse
import tifffile

def generate_samples(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    cases = {
        'isolated': [(55,55,12,9),(55,130,14,11),(60,220,10,16),(140,70,15,12),(140,170,11,9)],
        'touching': [(85,100,20,18),(85,128,20,18),(145,210,13,11)],
        'border': [(0,55,15,13),(95,120,17,12)],
        'blank': [],
    }
    for name, objects in cases.items():
        labels = np.zeros((200,300), dtype=np.uint32)
        rgb = np.full((200,300,3), [244,211,223], dtype=np.uint8)
        for i,(y,x,ry,rx) in enumerate(objects,1):
            rr,cc = ellipse(y,x,ry,rx,shape=labels.shape)
            labels[rr,cc] = i
            rgb[rr,cc] = [85,45,125]
        path = root / f'SYNTHETIC_{name}.png'
        if not path.exists(): Image.fromarray(rgb).save(path)
        refs = root / 'ground_truth'
        refs.mkdir(exist_ok=True)
        if not (refs / f'{name}_mask.png').exists():
            Image.fromarray((labels>0).astype(np.uint8)*255).save(refs / f'{name}_mask.png')
            tifffile.imwrite(refs / f'{name}_labels.tiff',labels)
        paths.append(path)
    (root/'synthetic_manifest.json').write_text(json.dumps({
        'notice':'Synthetic software fixtures, not BreaKHis or evidence of clinical accuracy.',
        'counts':{k:len(v) for k,v in cases.items()}},indent=2),encoding='utf-8')
    return paths
