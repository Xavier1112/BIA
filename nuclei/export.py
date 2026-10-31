"""Export snapshots into unique run directories; never overwrite source images."""
import csv
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import re
import uuid
import numpy as np
from PIL import Image
import tifffile
from . import __version__

BASE_FIELDS = ['label', 'centroid_x_px', 'centroid_y_px', 'area_px2', 'perimeter_px',
               'major_axis_px', 'minor_axis_px', 'eccentricity', 'solidity']

def write_csv(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else BASE_FIELDS)
    with Path(path).open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def new_run(root):
    path = Path(root) / (datetime.now().strftime('run_%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8])
    path.mkdir(parents=True, exist_ok=False)
    return path

def export_result(result, source, run_dir):
    source = Path(source)
    digest = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:12]
    stem = re.sub(r'[^\w.-]', '_', source.stem)[:80]
    folder = Path(run_dir) / f'{stem}_{digest}'
    folder.mkdir(parents=True, exist_ok=False)
    Image.fromarray(result.overlay()).save(folder / 'overlay.png')
    Image.fromarray(result.mask.astype(np.uint8) * 255).save(folder / 'mask.png')
    tifffile.imwrite(folder / 'labels.tiff', result.labels.astype(np.uint32), photometric='minisblack')
    fields = BASE_FIELDS + (['area_um2', 'perimeter_um', 'major_axis_um', 'minor_axis_um']
                            if result.config.microns_per_pixel is not None else [])
    write_csv(folder / 'nuclei.csv', result.rows, fields)
    summary = dict(source=str(source.resolve()), **result.summary)
    write_csv(folder / 'summary.csv', [summary])
    metadata = dict(application_version=__version__, created_utc=datetime.now(timezone.utc).isoformat(),
                    source=str(source.resolve()),
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None,
                    image_rgb_sha256=hashlib.sha256(result.image.tobytes()).hexdigest(),
                    config=asdict(result.config), summary=result.summary, warnings=result.warnings,
                    interpretation='Candidate regions, not verified nuclei or a diagnosis.',
                    versions={p: version(p) for p in ['numpy','scipy','scikit-image','Pillow','PySide6','matplotlib']})
    (folder / 'parameters.json').write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding='utf-8')
    return folder
