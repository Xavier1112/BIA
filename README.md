# BreaKHis Nuclei Explorer

A local Windows desktop demo for segmenting, counting and measuring **nucleus candidate regions** in H&E breast-biopsy images. It is an educational baseline, not a verified nucleus counter or diagnostic device. CPU only; no model training, credentials or runtime network connection is required.

## Start

On this computer, double-click `Launch.cmd`. On a new Windows computer install Python 3.12 with the Python launcher, then run `Setup.cmd` once (internet required for Python packages). Setup creates a project-local `.venv`; it does not change a shared Python environment. Run `Launch.cmd` after setup. Keep the whole project folder together.

Alternative: `.venv\Scripts\python.exe app.py`. If startup fails, Launch keeps the error message visible. Dependencies are pinned in `requirements.txt`; tests additionally use `requirements-dev.txt`.

## Try the GUI

1. Click **Synthetic examples** for four explicitly artificial fixtures with known masks, or **BreaKHis samples** for the downloaded real-image development subset.
2. Select a file, click **Analyze selected image**, and inspect the green candidate outlines beside the untouched original. Wheel zooms; drag pans; **Fit both images** resets the views.
3. Switch between outline, hematoxylin, binary mask and instance-label views. The table contains one row per retained region; the histogram shows its area distribution.
4. Adjust parameters and analyze again. Stale results cannot be exported after a parameter change.
5. **Export selected result** creates a unique run directory beneath your chosen folder.
6. **Open folder** recursively lists PNG/JPEG images. Choose a folder containing only input RGB images, not previous masks or exported overlays. **Analyze & export all listed images** writes one result set per image. Cancellation finishes the current image, preserves completed results and skips remaining images. Failures appear in the log and `failures.csv`.

## Course dataset

- Course link: https://www.kaggle.com/forderation/breakhis-400x
- Original database: https://web.inf.ufpr.br/vri/databases/breast-cancer-histopathological-database-BreakHis/
- Reference: Spanhol et al. (2016), *A Dataset for Breast Cancer Histopathological Image Classification*.

Download and unzip the course dataset, then select its image folder. If Kaggle requests authentication, complete that in your browser; this software does not collect credentials. Public file listing worked during development, but attempted legacy single-file download endpoints returned HTTP 404.

For an immediately usable small sample, `fetch_samples.py` downloads 12 images from the public PerceptiLabs mirror, whose README credits the course Kaggle dataset: https://github.com/PerceptiLabs/breakhis-400x . Its fixed commit, source URLs and SHA-256 hashes are saved in `data/breakhis_samples/manifest.json`. This mirror was not independently byte-matched against Kaggle. The selection covers benign/malignant subtypes and distinct specimen prefixes, not random sampling. It is for development and visual checks, not accuracy estimates. The original train/test folder labels do not make these images an independent validation set after inspecting or tuning on them.

Run `.venv\Scripts\python.exe fetch_samples.py` to recreate that sample if needed. Network errors stop the download with a visible error; use the course download instead. Keep data and results out of Git. Check the dataset's own terms before sharing images.

## Algorithm and parameters

The pure `analyze_image(uint8_rgb, AnalysisConfig) -> AnalysisResult` function is independent of Qt.

1. Apply scikit-image `rgb2hed` and take the hematoxylin channel, using the library's fixed stain matrix. This is a simple stain-separation baseline; stain vectors are not fitted to each slide.
2. Gaussian smoothing with sigma 1 px; min/max normalize this channel per image. Flat channels yield zero candidates.
3. Otsu threshold plus the offset below, clipped to [0,1]. Keep intensities strictly above the threshold.
4. Remove connected foreground components below minimum area; fill enclosed holes of at most 16 px.
5. Distance transform, local-maxima seeds and marker-controlled watershed. Ensure each component has a seed.
6. Filter resulting instances by area, then optionally by image-edge contact; relabel retained instances consecutively.

| Setting | Default | Interpretation |
|---|---:|---|
| Threshold offset | 0.00 | Positive retains stronger/darker hematoxylin; negative expands foreground. Per-image normalization means it is not a comparable absolute stain concentration. |
| Min area | 40 px2 | Removes tiny foreground components and small final instances. |
| Max area | 3000 px2 | Rejects large final instances; inspect merged nuclei before interpreting the count. |
| Separation | 8 px | Minimum peak spacing for seeds. Smaller may over-split; larger may merge neighbors. |
| Exclude edges | Off | Removes retained-size regions touching any image edge; reduces counts. |
| Calibration | Unknown | Supply measured micrometres per pixel only. 400x is not sufficient to calculate this. |

Defaults are starting points for 400x images, not biologically validated thresholds. Other magnifications need separate tuning. Dense overlapping nuclei, weak/variable staining, folds, dark debris and non-nuclear hematoxylin can cause errors. A smooth outline alone does not establish correctness. Counts include all detected nuclear-looking regions, not specifically tumor cells.

## Measurements and output

Pixel coordinates use x=column, y=row from the original upper-left corner. Areas are pixel counts, lengths are pixel-based region measurements; no resizing occurs during analysis. Perimeter uses scikit-image's pixel-grid perimeter estimator. Eccentricity and solidity are dimensionless. Coverage is retained foreground area divided by **whole image area**, not tissue-only area or cell density. Empty medians are null / blank.

Each result folder contains `overlay.png`, `mask.png` (0/255), `labels.tiff` (uint32, zero background, integer instance IDs), `nuclei.csv`, `summary.csv`, and `parameters.json` (parameters, warnings, versions, source and decoded-image hashes). Calibration adds area_um2 and calibrated lengths without replacing pixel values. A batch also writes `batch_summary.csv`, `failures.csv`, and `batch_report.json` including cancellation state. Each export gets a new directory; source-path hashes distinguish identical filenames. Files may be partial if disk writing fails; absence of `parameters.json` means export did not complete.

## Verification and annotation

Install development dependencies and run:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```

Tests cover synthetic isolated/touching objects, borders, blank images, invalid settings/files, Chinese paths, export round trips, batch errors/cancellation, independent overlap metrics and Qt result display/stale-state handling. See `VALIDATION.md` for the actual run record and limits.

For scientific evaluation, create a small held-out annotation set. Choose images or fixed crops before tuning and preserve full resolution. In an annotation tool such as FIJI, manually trace foreground nuclear boundaries and export a same-size grayscale PNG with 0 background and nonzero foreground. Save the original image/crop, annotate its filename and exact coordinates, observer and date, and separately count individual nuclei (touching nuclei must be counted individually). Use the same border-inclusion rule for both methods. Have a second group member review ambiguous regions; document disagreements. Do not use the software prediction as the supposedly independent reference.

```powershell
.venv\Scripts\python.exe evaluate.py --prediction results\example\mask.png --reference annotations\reference.png --predicted-count 100 --reference-count 110 --output evaluation.json
```

Dice/IoU here assess **binary foreground overlap**, not instance detection accuracy. Counts are independently supplied integers; absolute error alone cannot reveal compensating false positives/negatives. Both-empty masks score 1 by explicit convention and are flagged. Shape mismatch is rejected; no implicit alignment/resizing. BreaKHis tumor labels are not nuclear segmentation references. No accuracy claim should be made from the development subset or synthetic fixtures.

## Code map and collaboration

- `nuclei/core.py`: stain separation, segmentation, measurements.
- `nuclei/gui.py`: Qt presentation and parameter controls; `worker.py`: background batch processing.
- `nuclei/export.py`: output contracts and provenance; `synthetic.py`: reproducible fixtures.
- `tests/`, `evaluate.py`, `fetch_samples.py`: verification and data utilities.

Use real, incremental commits and reviews as your group develops this demo. Fill `CONTRIBUTIONS` with actual work; update `AI_use` with checks, changes and representative prompts. This demo is not a completed three-page course report.

Implementation references:
- https://scikit-image.org/docs/stable/auto_examples/color_exposure/plot_ihc_color_separation.html
- https://scikit-image.org/docs/stable/auto_examples/segmentation/plot_watershed.html
- https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.regionprops
- https://doc.qt.io/qtforpython-6/gettingstarted.html
