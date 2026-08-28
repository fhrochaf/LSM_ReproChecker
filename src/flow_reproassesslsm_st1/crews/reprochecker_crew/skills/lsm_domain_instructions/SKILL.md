---
name: landslide-mapping-domain-reference
description: Domain reference for the paper_analyzer agent when cataloging datasets and the paper's own novel method in a landslide mapping paper (used by analyze_paper). Consult this to recognize what role a dataset or method plays in the paper. This is reference material only — it does not define task steps or output formats; always follow the specific task's own description and expected_output.
---

# Landslide Mapping — Domain Reference

## Purpose
Background knowledge for `paper_analyzer` to consistently recognize and classify the
datasets and methods a landslide mapping paper actually uses, as opposed to what it
merely cites in passing. Use it alongside — never in place of — the calling task's own
instructions and output format.

## 1. Datasets: what to expect

A landslide mapping paper typically draws on two kinds of data:

**a) Landslide inventory (the reference/label data)**
Almost every paper has one. It is either:
- reused from a prior publication or public agency (cite the source), or
- developed by the authors themselves (e.g. field survey, manual photo-interpretation,
  a new inventory built specifically for this study).
Always catalog the inventory as a dataset in its own right, and note which of the two it is.

**b) Input datasets (what feeds the mapping/detection method)**
These are the actual inputs to the classifier or model. Common categories, useful for
recognizing what's being described even when the paper doesn't label it as a "dataset":
- Satellite imagery — optical (panchromatic/multispectral; note the sensor/mission,
  e.g. Sentinel-2, Landsat, PlanetScope) or SAR (note the sensor/mission, e.g.
  Sentinel-1, ALOS PALSAR)
- Elevation data — DEM/DTM, airborne or spaceborne LiDAR, photogrammetric DSMs
- Physical/terrain properties — rainfall/precipitation records, geological maps, soil
  characteristics, land cover, slope/aspect derivatives
- Any other custom input specific to that publication (e.g. InSAR displacement time
  series, UAV imagery, crowd-sourced imagery)

Catalog each input dataset separately, using its actual name/sensor as given in the paper.

## 2. Methods: what to expect

**a) The novel method (main target)**
This is the paper's own contribution — the mapping/detection method the paper is about.
Always catalog it, even if only briefly described. If the authors present variations of
it (different input combinations, channel sizes, preprocessing steps), treat
these as different entries and note the variations.

**b) Comparison methods**
Methods already published by other authors, run alongside the novel method for
benchmarking. Catalog these too, classified as reused from their original publication —
report the citation rather than re-describing the method.

## 3. Introduction-only mentions carry less weight

Datasets or methods that appear *only* in the introduction (e.g. background/related-work
citations, motivating examples) are literature review context, not necessarily something
the paper uses. Do not catalog them as used datasets/methods on that basis alone —
only include them if they are also referenced or used elsewhere in the paper (methods,
results, figures, tables, discussion). If a dataset or method appears solely in the
introduction, treat it as out of scope for cataloging.
