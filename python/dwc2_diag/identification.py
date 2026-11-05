# SPDX-License-Identifier: MIT
"""Versioned, source-backed identifier classification; no hardware operations."""
import json
from pathlib import Path


def database_path():
    return Path(__file__).resolve().parents[2] / 'data/device-identification-v1.json'


def load_database(path=None):
    data = json.loads(Path(path or database_path()).read_text())
    if data.get('schema') != 1 or not isinstance(data.get('devices'), list):
        raise ValueError('unsupported identification database')
    keys = set()
    for item in data['devices']:
        key = item['vendor_id'], item['product_id']
        if key in keys or any(type(x) is not int or not 0 <= x <= 65535 for x in key):
            raise ValueError('invalid or duplicate USB identity')
        keys.add(key)
        if item.get('identity_category') not in ('application', 'recovery', 'dfu', 'unknown', 'ambiguous') or item.get('state_category') not in ('application', 'recovery', 'dfu', 'unknown', 'ambiguous'):
            raise ValueError('missing supported state category')
        for source in item['sources']:
            if source not in data['sources']:
                raise ValueError('missing source reference')
    return data


def identify(vendor, product, database):
    for item in database['devices']:
        if item['vendor_id'] == vendor and item['product_id'] == product:
            return {**item, 'database_version': database['version'], 'model_verified': False,
                    'source_urls': [database['sources'][key]['url'] for key in item['sources']]}
    return {'vendor_id': vendor, 'product_id': product, 'label': 'Unknown USB identity',
            'mode': 'apple_unknown' if vendor == 0x05ac else 'unknown', 'confidence': 'unknown',
            'model': 'unverified', 'model_verified': False, 'sources': [], 'source_urls': [],
            'identity_category': 'unknown', 'state_category': 'unknown', 'state_verified': False,
            'evidence_basis': 'unclassified_observation',
            'database_version': database['version']}
