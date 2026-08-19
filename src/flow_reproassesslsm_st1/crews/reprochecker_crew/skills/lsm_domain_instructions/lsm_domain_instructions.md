---
name: landslide-mapping-domain-reference
description: Shared background reference on remote-sensing platforms, datasets, and method categories used in landslide mapping papers. Consult this to classify what a paper describes (filtering) or what kind of data/method it uses (reproducibility checks). This is reference material only — it does not define task steps or output formats; always follow the specific task's own description and expected_output.
---

# Landslide Mapping — Domain Reference

## Purpose
Background knowledge to keep classification consistent across the filtering and
reproducibility-check agents. Use it to recognize and label what's in a paper — not as a
substitute for any task's own instructions or expected output format.

**Sources:**
- Guzzetti et al. (2012), *Landslide inventory maps: New tools for an old problem*,
  Earth-Science Reviews 112, 42–66. https://doi.org/10.1016/j.earscirev.2012.02.001
- Novellino et al. (2024), *Mapping landslides from space: A review*, Landslides 21,
  1041–1052. https://doi.org/10.1007/s10346-024-02215-x

## 1. Remote-sensing platforms and datasets
Relevant for `data_reproducibility_checker`. Landslide-mapping datasets typically fall
into one or more of these categories — useful for recognizing what's being described,
regardless of whether the paper names it explicitly as a "dataset":

- Aerial photography (stereo pairs, scale, acquisition dates)
- Airborne LiDAR (point density/GSD, DEM/DTM derivatives)
- Terrestrial sensing (laser rangefinder + GPS, terrestrial laser scanning)
- Optical satellite imagery — panchromatic or multispectral (mission, GSD, bands,
  revisit time)
- SAR satellite imagery (mission, wavelength, polarization)
- UAV/drone imagery (resolution, altitude)
- Crowd-sourced/web-mapping imagery (Google Earth, Bing Maps, social media)
- Pre-existing landslide inventories used as reference/validation data

For each, the source/provider and any retrieval link or access statement are what
determine availability — this reference only helps identify *what kind* of dataset is
being described.

## 2. Method categories
Relevant for `method_reproducibility_checker`. These map directly onto that task's four
output types — use them to recognize which bucket a described method falls into:

- **Manual / heuristic visual interpretation** (shape, tone, texture, pattern
  recognition by a human analyst) → typically a **manual method**.
- **Workflow executed through existing, named GIS/remote-sensing software** with no
  custom coding → typically a **software-based method**.
- **Pixel-based indexing/thresholding, change detection, OBIA/segmentation, DEM
  morphometric analysis, InSAR/displacement measurement, or machine learning (including
  deep learning, AI methods, etc.)** implemented as a custom pipeline → typically a **custom/code-based method**
  (check for accompanying code/repository).
- **A method explicitly adopted unchanged from a prior publication** → a **reused
  method** (locate the original citation rather than re-describing it).

Note: a single paper may combine categories (e.g., manual delineation on top of an
automated pre-processing pipeline) — identify each component rather than forcing the
whole paper into one bucket.

## Pitfalls
- Don't conflate the sensor/dataset with the technique — the same imagery can support
  very different methods (manual, software-based, custom, or reused).
- Don't classify a paper as a mapping-method paper just because it mentions remote
  sensing data — check it actually proposes/applies a detection technique (see §1).
- Susceptibility mapping and mapping methods are easy to conflate when both use similar
  input layers; the distinguishing question is "does this map landslides that occurred,
  or predict where they might occur?"
- UAV-based methods are only lightly covered by the two reference sources above —
  classify using the same categories, but don't assume the taxonomy is exhaustive for
  this platform.