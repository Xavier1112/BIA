import csv
import json
from dataclasses import replace
import numpy as np
from PIL import Image
import pytest
import tifffile
from nuclei.core import analyze_image, AnalysisConfig, read_image, discover_images
from nuclei.synthetic import generate_samples
from nuclei.export import new_run, export_result
from nuclei.worker import AnalysisWorker
from evaluate import evaluate_masks

@pytest.fixture
def samples(tmp_path): return generate_samples(tmp_path/'合成样本')

def test_isolated_and_touching(samples):
    for path,expected in zip(samples[:2],[5,3]):
        r=analyze_image(read_image(path))
        assert r.summary['candidate_count']==expected
        assert np.array_equal(np.unique(r.labels),np.arange(expected+1))
        assert all(x['area_px2']>40 for x in r.rows)

def test_border_and_blank(samples):
    edge=read_image(samples[2])
    assert analyze_image(edge).summary['candidate_count']==2
    r=analyze_image(edge,AnalysisConfig(exclude_border=True))
    assert r.summary['candidate_count']==1 and r.summary['rejected_border']==1
    for image in [read_image(samples[3]),np.full((40,50,3),255,np.uint8),np.zeros((40,50,3),np.uint8)]:
        result=analyze_image(image)
        assert not result.mask.any() and result.warnings
        assert result.summary['median_area_px2'] is None

def test_calibration_and_preserve_input(samples):
    image=read_image(samples[0]); original=image.copy()
    r=analyze_image(image,AnalysisConfig(microns_per_pixel=.5))
    assert np.array_equal(image,original)
    assert r.rows[0]['area_um2']==r.rows[0]['area_px2']*.25
    assert r.rows[0]['major_axis_um']==r.rows[0]['major_axis_px']*.5

def test_filter_and_invalid_config(samples):
    image=read_image(samples[0])
    r=analyze_image(image,AnalysisConfig(max_area=100))
    assert r.summary['rejected_large']==5 and not r.rows
    for c in [AnalysisConfig(min_area=400,max_area=100),AnalysisConfig(separation=0),
              AnalysisConfig(microns_per_pixel=float('nan'))]:
        with pytest.raises(ValueError): analyze_image(image,c)
    with pytest.raises(ValueError): analyze_image(image.astype(float))

def test_export_roundtrip_and_same_names(samples,tmp_path):
    r=analyze_image(read_image(samples[0]))
    run=new_run(tmp_path/'exports')
    output=export_result(r,samples[0],run)
    assert np.array_equal(tifffile.imread(output/'labels.tiff'),r.labels)
    with Image.open(output/'mask.png') as im: assert np.array_equal(np.asarray(im)>0,r.mask)
    with Image.open(output/'overlay.png') as im: assert im.size==(300,200)
    with (output/'nuclei.csv').open(encoding='utf-8-sig') as f:
        assert len(list(csv.DictReader(f)))==r.summary['candidate_count']
    assert json.loads((output/'parameters.json').read_text())['config']['min_area']==40
    other=tmp_path/'other'/samples[0].name
    assert export_result(r,other,run)!=output
    with pytest.raises(FileExistsError): export_result(r,samples[0],run)

def test_read_errors_and_recursive_discovery(samples,tmp_path):
    bad=tmp_path/'broken.png'; bad.write_bytes(b'not an image')
    with pytest.raises(Exception): read_image(bad)
    gray=tmp_path/'gray.png'; Image.new('L',(10,10)).save(gray)
    with pytest.raises(ValueError): read_image(gray)
    assert samples[0] in discover_images(tmp_path)

def test_batch_failure_and_cancellation(samples,tmp_path):
    bad=tmp_path/'bad.png'; bad.write_bytes(b'bad')
    run=new_run(tmp_path/'out')
    worker=AnalysisWorker([samples[0],bad,samples[1]],AnalysisConfig(),run)
    worker.run()
    report=json.loads((run/'batch_report.json').read_text())
    assert len(report['success'])==2 and len(report['failures'])==1
    cancelled=new_run(tmp_path/'out')
    worker=AnalysisWorker(samples,AnalysisConfig(),cancelled)
    worker.progress.connect(lambda *args:worker.cancel_event.set())
    worker.run()
    report=json.loads((cancelled/'batch_report.json').read_text())
    assert report['cancelled'] and len(report['success'])==1

def test_metrics():
    a=np.array([[1,0],[0,1]],dtype=np.uint8); b=np.array([[1,0],[0,0]])
    report=evaluate_masks(a,b,2,1)
    assert report['dice']==pytest.approx(2/3) and report['iou']==.5
    assert report['count_absolute_error']==1
    assert evaluate_masks(a*0,b*0)['dice']==1
    with pytest.raises(ValueError): evaluate_masks(a,np.zeros((3,3)))
