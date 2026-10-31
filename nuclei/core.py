"""Pure analysis functions. Coordinates are x=column, y=row in the original image."""
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import color, filters, measure, segmentation, feature

MAX_PIXELS = 16_000_000

@dataclass(frozen=True)
class AnalysisConfig:
    threshold_offset: float = 0.0  # Fraction of normalized hematoxylin intensity
    min_area: int = 40
    max_area: int = 3000
    separation: int = 8
    exclude_border: bool = False
    microns_per_pixel: float | None = None

    def validate(self):
        if not -0.3 <= self.threshold_offset <= 0.3:
            raise ValueError("Threshold offset must be between -0.30 and 0.30.")
        if not 1 <= self.min_area <= self.max_area:
            raise ValueError("Minimum area must be positive and no greater than maximum area.")
        if not 1 <= self.separation <= 100:
            raise ValueError("Separation must be between 1 and 100 pixels.")
        if self.microns_per_pixel is not None and (
            not np.isfinite(self.microns_per_pixel) or self.microns_per_pixel <= 0
        ):
            raise ValueError("Calibration must be a finite, positive microns/pixel value.")

@dataclass
class AnalysisResult:
    image: np.ndarray
    hematoxylin: np.ndarray
    labels: np.ndarray
    rows: list[dict]
    summary: dict
    warnings: list[str]
    config: AnalysisConfig

    @property
    def mask(self):
        return self.labels > 0

    def overlay(self):
        out = self.image.copy()
        out[segmentation.find_boundaries(self.labels, mode="inner")] = [0, 255, 170]
        return out

def read_image(path):
    path = Path(path)
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Choose an RGB PNG or JPEG image.")
    with Image.open(path) as im:
        if im.width * im.height > MAX_PIXELS:
            raise ValueError("Image exceeds 16 million pixels; use a documented crop.")
        if im.mode not in {"RGB", "RGBA"}:
            raise ValueError("H&E stain separation requires an RGB image (not grayscale/palette).")
        if im.mode == "RGBA":
            background = Image.new("RGBA", im.size, "white")
            im = Image.alpha_composite(background, im)
        return np.asarray(im.convert("RGB")).copy()

def discover_images(folder):
    return sorted(p for p in Path(folder).rglob("*")
                  if p.is_file() and not p.is_symlink()
                  and p.suffix.lower() in {".png", ".jpg", ".jpeg"})

def analyze_image(image, config=None):
    config = config or AnalysisConfig()
    config.validate()
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("Expected an H x W x 3 uint8 RGB image.")
    if min(image.shape[:2]) < 3 or image.shape[0] * image.shape[1] > MAX_PIXELS:
        raise ValueError("Image dimensions are outside supported limits.")
    image = image.copy()
    warnings = []
    h = color.rgb2hed(image)[..., 0]
    h = filters.gaussian(h, sigma=1.0, preserve_range=True)
    low, high = float(h.min()), float(h.max())
    labels = np.zeros(h.shape, dtype=np.int32)
    rejected = dict(rejected_small=0, rejected_large=0, rejected_border=0,
                    removed_small_components=0)
    threshold = None
    if high - low < 1e-6:
        h = np.zeros_like(h)
        warnings.append("No hematoxylin contrast: zero candidates returned.")
    else:
        h = (h - low) / (high - low)
        threshold = float(np.clip(filters.threshold_otsu(h) + config.threshold_offset, 0, 1))
        mask = h > threshold
        components, _ = ndi.label(mask)
        sizes = np.bincount(components.ravel())
        small = np.flatnonzero((sizes < config.min_area) & (np.arange(len(sizes)) > 0))
        rejected["removed_small_components"] = len(small)
        mask[np.isin(components, small)] = False
        # Fill only small enclosed holes; never fill the surrounding background.
        holes, _ = ndi.label(~mask)
        edge_holes = np.unique(np.concatenate([holes[0], holes[-1], holes[:, 0], holes[:, -1]]))
        hole_sizes = np.bincount(holes.ravel())
        fill = np.flatnonzero(hole_sizes <= 16)
        fill = np.setdiff1d(fill, np.r_[0, edge_holes])
        mask[np.isin(holes, fill)] = True
        if np.any(mask):
            distance = ndi.distance_transform_edt(mask)
            components, _ = ndi.label(mask)
            peaks = feature.peak_local_max(distance, min_distance=config.separation,
                                          labels=components, exclude_border=False)
            markers = np.zeros(mask.shape, dtype=np.int32)
            for index, (y, x) in enumerate(peaks, 1):
                markers[y, x] = index
            # Ensure every connected component has at least one marker.
            marker_id = int(markers.max())
            for obj in measure.regionprops(components):
                ys, xs = obj.coords.T
                if not np.any(markers[ys, xs]):
                    best = np.argmax(distance[ys, xs])
                    marker_id += 1
                    markers[ys[best], xs[best]] = marker_id
            raw = segmentation.watershed(-distance, markers, mask=mask)
            next_label = 0
            for obj in measure.regionprops(raw):
                y0, x0, y1, x1 = obj.bbox
                if obj.area < config.min_area:
                    rejected["rejected_small"] += 1
                elif obj.area > config.max_area:
                    rejected["rejected_large"] += 1
                elif config.exclude_border and (y0 == 0 or x0 == 0 or
                                                y1 == mask.shape[0] or x1 == mask.shape[1]):
                    rejected["rejected_border"] += 1
                else:
                    next_label += 1
                    ys, xs = obj.coords.T
                    labels[ys, xs] = next_label
        else:
            warnings.append("Threshold and filtering produced an empty mask.")
    rows = []
    for obj in measure.regionprops(labels):
        row = dict(label=int(obj.label), centroid_x_px=float(obj.centroid[1]),
                   centroid_y_px=float(obj.centroid[0]), area_px2=float(obj.area),
                   perimeter_px=float(obj.perimeter), major_axis_px=float(obj.axis_major_length),
                   minor_axis_px=float(obj.axis_minor_length), eccentricity=float(obj.eccentricity),
                   solidity=float(obj.solidity))
        scale = config.microns_per_pixel
        if scale is not None:
            row.update(area_um2=row["area_px2"] * scale**2,
                       perimeter_um=row["perimeter_px"] * scale,
                       major_axis_um=row["major_axis_px"] * scale,
                       minor_axis_um=row["minor_axis_px"] * scale)
        rows.append(row)
    if rejected["rejected_large"]:
        warnings.append("Large regions were rejected; inspect possible merged nuclei.")
    if not rows and not warnings:
        warnings.append("No candidates remain after area/border filtering.")
    summary = dict(candidate_count=len(rows),
                   median_area_px2=float(np.median([r["area_px2"] for r in rows])) if rows else None,
                   coverage_percent=float(100 * np.mean(labels > 0)),
                   width_px=image.shape[1], height_px=image.shape[0],
                   normalized_threshold=threshold, **rejected)
    if config.microns_per_pixel is not None:
        summary["median_area_um2"] = (summary["median_area_px2"] * config.microns_per_pixel**2
                                      if rows else None)
    return AnalysisResult(image, h, labels, rows, summary, warnings, config)
