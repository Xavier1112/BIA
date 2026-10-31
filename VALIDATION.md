# Verification record

Date: 2026-10-31. Platform: Windows, Python 3.12.14, CPU execution.
Exact installed packages: requirements-lock.txt. This record describes an AI-assisted
development check, not independent human assessment of segmentation accuracy.

## Completed checks

- `python -m pytest -q`: **9 passed** (latest run 1.89 seconds).
- `python -m pip check`: no broken requirements.
- Synthetic isolated objects: expected 5, detected 5. Touching fixture: expected 3,
  detected 3. Border exclusion removes the known edge object. Uniform inputs return
  zero with a warning. Input arrays are unchanged.
- Invalid settings, corrupt files, grayscale input, Chinese paths, calibration,
  label/mask/CSV round trips and collision handling tested.
- Batch continuation after a corrupt image and cancellation between images tested.
- Qt integration tested: result display, measurement rows, all four views, and
  disabling export after parameter changes.
- Launch.cmd opened an actual desktop window. Desktop interaction verified loading
  real samples, running analysis, displaying the measurement table and histogram,
  selecting an export folder, and saving the result.
- Actual GUI batch run: **12 successful exports, 0 failures, not cancelled**.
  Record: results/run_20261031_004404_f3ff6a8d/batch_report.json.
  All 12 exported label files were reopened and checked against CSV row counts
  and the batch candidate counts; all matched.
- Single-image GUI export: results/run_20261031_004313_ae35a326/.

## Real-image development sample

12 images (6 benign, 6 malignant) were obtained from the PerceptiLabs mirror of the
course dataset. Fixed mirror commit and hashes are in data/breakhis_samples/manifest.json.
The mirror README credits the course Kaggle dataset; byte identity against Kaggle
was not independently established. No credentials were used. The samples are for
development, not an independent accuracy test set.

All images were analyzed at original resolution with the documented defaults, and
exported labels were read back and checked. Core analysis took 0.058–0.291 seconds
per image on this computer, excluding export and GUI rendering. Candidate counts
ranged from 26 to 266; these are algorithm outputs, not known true counts.

Detailed timings, settings, outputs and three visually inspected contact sheets:
results/real_smoke/run_20261031_003949_2ef15cbc/.

## Visual observations and limitations

- Clearly separated dark nuclei were often delineated in DC-14-10926 and MC-14-10147.
- Dense A/PT/PC regions showed merged boundaries and fragmentation; PC-14-12465
  particularly illustrated over-segmentation and non-nuclear foreground.
- F-14-14134 showed elongated/background structures included as candidates.
- LC examples showed pale nuclei not retained by the default threshold.
- DC-14-11031 showed fragmented interiors in some nuclei.

These observations are qualitative software-development inspection, not pathologist
ground truth. No Dice, IoU, sensitivity, specificity, or clinical accuracy is claimed
on real images. Defaults were retained after inspection, not optimized to produce
better-looking results. Parameters are intentionally adjustable.

## Work for the student group

Create independent, same-resolution nuclear masks and manual counts, using the
README annotation protocol. Freeze parameters before evaluating a held-out set.
Use evaluate.py for binary overlap and count error, documenting exclusions and
observer disagreements. Review the algorithm and tests, make actual contributions,
and fill CONTRIBUTIONS and the student-verification sections of AI_use.

The complete Kaggle dataset, independent manual annotations, a clinical validation,
and a standalone executable installer have not been produced by this demo.
