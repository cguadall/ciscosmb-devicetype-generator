# ciscosmb-devicetype-generator
This set of scripts helped me generate device type definitions and images for Cisco Catalyst 1200 and 1300 series switches and Cisco Business CBS250/CBS350 series switches. Generated in part by ChatGPT.

These definitions are destined for the [NetBox devicetype-library](https://github.com/netbox-community/devicetype-library)

These scripts can be adapted for other models/manufacturers for bulk creation of different model series.

It consists of
* `generate.py` -- uses a predefined `models.csv` file to produce templates appropriate for devicetype-library
* `crop.py` -- a Pillow-based cropping tool to create NetBox-friendly rear and front images from manufacturer images
* `models.csv` -- input file containing model metadata for both Catalyst 1200 and 1300 series

## Usage

Generate YAML files from the CSV:

```bash
python generate.py --csv models.csv
```

`generate.py` auto-detects model series by prefix (`C1200` / `C1300`) and defaults to Catalyst 1300 behavior for unknown prefixes.

Supported model prefixes include `C1200`, `C1300`, `C1300X`, `CBS250`, and `CBS350`.

Normalize elevation PNG images to a 10:1 aspect ratio:

```bash
python -c "import crop; crop.process_directory('elevation-images', overwrite=True)"
```

Manual image workflow:

1. Import vendor images into `elevation-images/`.
2. Rename each file to `cisco-<model-slug>.front.png` or `cisco-<model-slug>.rear.png`.
3. Run `crop.py` normalization so every image is NetBox-friendly (10:1).

Examples:

* `cisco-c1300x-24t-4x.front.png`
* `cisco-c1300x-24t-4x.rear.png`