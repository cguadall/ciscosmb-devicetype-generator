#!/usr/bin/env python3

import csv
import re
import os
import argparse
import html
import urllib.request
import urllib.error

try:
    import yaml
except ImportError:
    print("Please install PyYAML (e.g., pip install pyyaml).")
    raise SystemExit

class IndentDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(IndentDumper, self).increase_indent(flow, False)

def slugify(s):
    """
    Convert a string to a slug safe for filenames and YAML 'slug' fields:
      - Lowercase
      - Replace non-alphanumeric characters with '-'
      - Collapse multiple dashes
      - Strip leading/trailing dashes
    """
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


SERIES_META = {
    '1200': {
        'prefix': 'C1200',
        'label': 'Catalyst 1200',
        'datasheet_url': 'https://www.cisco.com/c/en/us/products/collateral/switches/catalyst-1200-series-switches/nb-06-cat1200-ser-data-sheet-cte-en.html',
    },
    '1300': {
        'prefix': 'C1300',
        'label': 'Catalyst 1300',
        'datasheet_url': 'https://www.cisco.com/c/en/us/products/collateral/switches/catalyst-1300-series-switches/nb-06-cat1300-ser-data-sheet-cte-en.html',
    },
    'cbs250': {
        'prefix': 'CBS250',
        'label': 'CBS250',
        'datasheet_url': 'https://www.cisco.com/c/en/us/products/collateral/switches/business-250-series-smart-switches/cbs250-ds.html',
    },
    'cbs350': {
        'prefix': 'CBS350',
        'label': 'CBS350',
        'datasheet_url': 'https://www.cisco.com/c/en/us/products/collateral/switches/business-350-series-managed-switches/cbs350-ds.html',
    },
}


FANLESS_KEYWORDS = [
    'FANLESS',
    'NO FAN',
    'WITHOUT FAN',
]

FAN_KEYWORDS = [
    'FAN',
    'FANS',
    'COOLING FAN',
    'VARIABLE SPEED FAN',
]

DIRECTION_KEYWORDS = {
    'front-to-rear': [
        'FRONT-TO-REAR',
        'FRONT TO REAR',
        'FRONT-TO-BACK',
        'FRONT TO BACK',
    ],
    'rear-to-front': [
        'REAR-TO-FRONT',
        'REAR TO FRONT',
        'BACK-TO-FRONT',
        'BACK TO FRONT',
    ],
    'left-to-right': [
        'LEFT-TO-RIGHT',
        'LEFT TO RIGHT',
    ],
    'right-to-left': [
        'RIGHT-TO-LEFT',
        'RIGHT TO LEFT',
    ],
    'side-to-rear': [
        'SIDE-TO-REAR',
        'SIDE TO REAR',
    ],
}


def get_series_metadata(model, default_series='1300'):
    model_upper = model.upper()
    for series, meta in SERIES_META.items():
        if model_upper.startswith(meta['prefix']):
            return meta

    # Default to Catalyst 1300 behavior unless explicitly overridden.
    return SERIES_META.get(default_series, SERIES_META['1300'])


def fetch_datasheet_text(url, cache):
    """
    Fetch datasheet HTML and return a normalized uppercase plain-text body.
    Results are cached per URL to avoid repeated network calls.
    """
    if url in cache:
        return cache[url]

    try:
        request = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; cisco-devicetype-generator/1.0)'
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode('utf-8', errors='ignore')
    except (urllib.error.URLError, TimeoutError, ValueError):
        cache[url] = ''
        return ''

    body = re.sub(r'(?is)<script.*?>.*?</script>', ' ', body)
    body = re.sub(r'(?is)<style.*?>.*?</style>', ' ', body)
    body = re.sub(r'(?is)<[^>]+>', ' ', body)
    body = html.unescape(body)
    body = re.sub(r'\s+', ' ', body).strip().upper()

    cache[url] = body
    return body


def model_variants(model):
    """Return model string variants commonly present in datasheet tables/text."""
    base = model.upper()
    variants = {
        base,
        base.replace('-', ' '),
        base.replace('-', ''),
    }
    return [v for v in variants if v]


def extract_model_contexts(text, model, context_window=220):
    """Extract nearby text windows around model references."""
    contexts = []
    for variant in model_variants(model):
        start = 0
        while True:
            idx = text.find(variant, start)
            if idx == -1:
                break
            left = max(0, idx - context_window)
            right = min(len(text), idx + len(variant) + context_window)
            contexts.append(text[left:right])
            start = idx + len(variant)

    return contexts


def infer_airflow_from_datasheet(model, datasheet_url, cache):
    """
    Determine airflow from Cisco datasheet text.

    Rules:
      1) If model context includes fanless terms => passive.
      2) If model context includes explicit airflow direction => that direction.
      3) If model context includes fan references => front-to-rear.
      4) If not found/ambiguous => None (caller applies fallback).
    """
    text = fetch_datasheet_text(datasheet_url, cache)
    if not text:
        return None

    contexts = extract_model_contexts(text, model)
    if not contexts:
        return None

    for context in contexts:
        if any(keyword in context for keyword in FANLESS_KEYWORDS):
            return 'passive'

    for context in contexts:
        for direction, keywords in DIRECTION_KEYWORDS.items():
            if any(keyword in context for keyword in keywords):
                return direction

    for context in contexts:
        if any(keyword in context for keyword in FAN_KEYWORDS):
            return 'front-to-rear'

    return None

def create_interfaces(row):
    """
    Build a list of interface definitions from the counts in the CSV row,
    using different naming conventions depending on whether 'Stacking' is true or false.
    """

    # Determine if stacking is enabled
    stacking_str = row.get('Stacking', '').strip().lower()
    is_stacking = (stacking_str == 'true')

    # If stacking, use e.g. "GigabitEthernet1/0/#"; if not, just "GigabitEthernet#".
    if is_stacking:
        base_name_1g = "GigabitEthernet1/0/"
        base_name_10g = "TenGigabitEthernet1/0/"
    else:
        base_name_1g = "GigabitEthernet"
        base_name_10g = "TenGigabitEthernet"

    interfaces = []
    int_index_1g = 1   # For 1G (and multi-gig) ports
    int_index_10g = 1  # For 10G ports

    # A simple PoE detection: if the Model has 'P-' or 'FP-' in its name, assume PoE.
    model_name = row['Model'].upper()
    is_poe = ('P-' in model_name or 'FP-' in model_name)

    # 1) GigabitEthernet Copper
    num_gi_copper = int(row['GigabitEthernet Copper'])
    for _ in range(num_gi_copper):
        iface = {
            'name': f"{base_name_1g}{int_index_1g}",
            'type': '1000base-t',
            'enabled': True
        }
        if is_poe:
            iface['poe_mode'] = 'pse'
            iface['poe_type'] = 'type2-ieee802.3at'
        interfaces.append(iface)
        int_index_1g += 1

    #
    # 2) GigabitEthernet SFP (dedicated 1G fiber ports)
    #
    num_gi_sfp = int(row['GigabitEthernet SFP'])
    for _ in range(num_gi_sfp):
        iface = {
            'name': f"{base_name_1g}{int_index_1g}",
            'type': '1000base-x-sfp',
            'enabled': True
        }
        interfaces.append(iface)
        int_index_1g += 1

    #
    # 3) GigabitEthernet Combo (RJ-45/SFP 1G combo ports)
    #
    num_gi_combo = int(row['GigabitEthernet Combo'])
    for _ in range(num_gi_combo):
        iface = {
            'name': f"{base_name_1g}{int_index_1g}",
            # Custom type to indicate 1G copper/SFP combo in one port:
            'type': '1000base-x-sfp',
            'description': 'SFP/RJ45 Combo',
            'enabled': True
        }
        interfaces.append(iface)
        int_index_1g += 1

    #
    # 4) TwoGigabitEthernet (2.5G, etc.) - multi-gig
    #
    num_two_gi = int(row['TwoGigabitEthernet'])
    for _ in range(num_two_gi):
        # We'll name them as part of the same 1G numbering, but with type 2.5gbase-t
        iface = {
            'name': f"{base_name_1g}{int_index_1g}",
            'type': '2.5gbase-t',
            'enabled': True
        }
        interfaces.append(iface)
        int_index_1g += 1

    #
    # 5) TenGigabitEthernet Copper
    #
    num_ten_gi_copper = int(row['TenGigabitEthernet Copper'])
    for _ in range(num_ten_gi_copper):
        iface = {
            'name': f"{base_name_10g}{int_index_10g}",
            'type': '10gbase-t',
            'enabled': True
        }
        interfaces.append(iface)
        int_index_10g += 1

    #
    # 6) TenGigabitEthernet SFP+
    #
    num_ten_gi_sfp = int(row['TenGigabitEthernet SFP+'])
    for _ in range(num_ten_gi_sfp):
        iface = {
            'name': f"{base_name_10g}{int_index_10g}",
            'type': '10gbase-x-sfpp',
            'enabled': True
        }
        interfaces.append(iface)
        int_index_10g += 1

    #
    # 7) TenGigabitEthernet Combo (10G copper/SFP+ combo)
    #
    num_ten_gi_combo = int(row['TenGigabitEthernet Combo'])
    for _ in range(num_ten_gi_combo):
        iface = {
            'name': f"{base_name_10g}{int_index_10g}",
            'type': '10gbase-x-sfpp',
            'description': 'SFP+/RJ45 Combo',            
            'enabled': True
        }
        interfaces.append(iface)
        int_index_10g += 1

    #
    # 8) OOB interface (if any)
    #
    if row['OOB'] and row['OOB'].isdigit() and int(row['OOB']) > 0:
        iface = {
            'name': 'OOB',
            'type': '1000base-t',
            'enabled': True,
            'mgmt_only': True
        }
        interfaces.append(iface)

    #
    # 9) Add a default VLAN interface for management (like Vlan1).
    #
    interfaces.append({
        'name': 'Vlan1',
        'type': 'virtual',
        'enabled': True,
        'mgmt_only': False
    })

    return interfaces

def create_console_ports(row):
    """
    Build a list of console port definitions from con0, con1, con2 columns if they are non-empty.
    """
    console_ports = []
    for c in ['con0', 'con1', 'con2']:
        ctype = row.get(c, '').strip()
        if ctype:
            console_ports.append({
                'name': c,
                'type': ctype
            })
    return console_ports

def main(csv_filename='models.csv', default_series='1300'):
    datasheet_cache = {}

    with open(csv_filename, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row['Model']
            part_number = model
            # Build the slug from the model name
            device_slug = f"cisco-{slugify(model)}"

            filename = model.upper()

            series_meta = get_series_metadata(model, default_series)

            # Keep Cisco device type naming convention in NetBox device-type library.
            model = model.replace(series_meta['prefix'], series_meta['label'])

            weight_lbs = float(row['Weight (pounds)'])

            # Draw is in watts
            max_draw = int(round(float(row['Draw'])))

            airflow = infer_airflow_from_datasheet(
                part_number,
                series_meta['datasheet_url'],
                datasheet_cache,
            )
            if airflow is None:
                airflow = 'front-to-rear'
                print(f"Warning: airflow not found in datasheet for {part_number}. Using fallback '{airflow}'.")

            # Build the device dictionary
            device_dict = {
                'manufacturer': 'Cisco',
                'model': model,
                'slug': device_slug,
                'part_number': part_number,
                'u_height': 1.0,
                'is_full_depth': False,
                'front_image': False,
                'rear_image': False,
                'airflow': airflow,
                'comments': f"[{series_meta['label']} Datasheet]({series_meta['datasheet_url']})",
                'weight': weight_lbs,
                'weight_unit': 'lb',
                'interfaces': create_interfaces(row),
                'console-ports': create_console_ports(row),
                'power-ports': [
                    {
                        'name': 'PSU0',
                        'type': row['psu0'],
                        'maximum_draw': max_draw
                    }
                ],
            }

            # Check for front and rear images named using the device slug
            front_path = os.path.join("elevation-images", f"{device_slug.lower()}.front.png")
            rear_path  = os.path.join("elevation-images", f"{device_slug.lower()}.rear.png")

            front_exists = os.path.isfile(front_path)
            rear_exists = os.path.isfile(rear_path)

            if front_exists:
                device_dict['front_image'] = True
            if rear_exists:
                device_dict['rear_image'] = True

            # Dump to YAML
            yaml_string = yaml.dump(device_dict, sort_keys=False, Dumper=IndentDumper, allow_unicode=True)

            out_filename = "Cisco/" + filename + f".yaml"
            with open(out_filename, 'w', encoding='utf-8') as out_f:
                out_f.write("---\n")
                out_f.write(yaml_string)

            print(f"Generated {out_filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generate NetBox device type YAML from models.csv for Catalyst 1200/1300 and CBS250/CBS350.'
    )
    parser.add_argument(
        '--csv',
        default='models.csv',
        help='Path to the input CSV file (default: models.csv).'
    )
    parser.add_argument(
        '--default-series',
        choices=['1200', '1300', 'cbs250', 'cbs350'],
        default='1300',
        help='Fallback series when model prefix is not recognized (default: 1300).'
    )

    args = parser.parse_args()
    main(csv_filename=args.csv, default_series=args.default_series)
