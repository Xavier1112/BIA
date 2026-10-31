"""Compare same-size foreground masks, with optional independently supplied counts."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image

def evaluate_masks(prediction, reference, predicted_count=None, reference_count=None):
    p=np.asarray(prediction); r=np.asarray(reference)
    if p.ndim!=2 or r.ndim!=2 or p.shape!=r.shape:
        raise ValueError('Masks must be two-dimensional and have exactly the same shape; no resizing.')
    p=p>0; r=r>0
    intersection=int(np.sum(p&r)); union=int(np.sum(p|r)); total=int(p.sum()+r.sum())
    result=dict(dice=2*intersection/total if total else 1.0,
                iou=intersection/union if union else 1.0,
                empty_reference=not bool(r.any()),
                note='Foreground overlap, not instance matching. Both empty is defined as 1.')
    if (predicted_count is None)!=(reference_count is None):
        raise ValueError('Supply both counts or neither.')
    if predicted_count is not None:
        if min(predicted_count,reference_count)<0: raise ValueError('Counts must be nonnegative.')
        result.update(predicted_count=predicted_count,reference_count=reference_count,
                      count_absolute_error=abs(predicted_count-reference_count))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prediction',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--predicted-count',type=int)
    parser.add_argument('--reference-count',type=int)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    with Image.open(args.prediction) as im: p=np.asarray(im).copy()
    with Image.open(args.reference) as im: r=np.asarray(im).copy()
    report=evaluate_masks(p,r,args.predicted_count,args.reference_count)
    text=json.dumps(report,indent=2)
    if args.output:
        with args.output.open('x',encoding='utf-8') as f: f.write(text)
    print(text)

if __name__=='__main__': main()
