# SPDX-License-Identifier: MIT
"""Strict cached USB descriptor parsing. Never sends a USB transaction."""


class DescriptorError(ValueError):
    pass


def le16(blob, offset):
    return int.from_bytes(blob[offset:offset + 2], 'little')


def device_descriptor(blob):
    if len(blob) != 18 or blob[0:2] != bytes((18, 1)) or not blob[17]:
        raise DescriptorError('invalid device descriptor length/type/configuration count')
    return {'usb_bcd': le16(blob, 2), 'class': blob[4], 'subclass': blob[5], 'protocol': blob[6],
            'max_packet_size0': blob[7], 'vendor_id': le16(blob, 8), 'product_id': le16(blob, 10),
            'device_bcd': le16(blob, 12), 'manufacturer_index': blob[14], 'product_index': blob[15],
            'serial_index': blob[16], 'configurations': blob[17], 'raw': blob.hex()}


def configuration_descriptor(blob, usb_bcd=0x200):
    if (len(blob) < 9 or blob[:2] != bytes((9, 2)) or le16(blob, 2) != len(blob)
            or not blob[5] or not blob[7] & 0x80):
        raise DescriptorError('invalid configuration header/length/attributes')
    result = {'value': blob[5], 'interface_count': blob[4], 'string_index': blob[6],
              'attributes': blob[7], 'self_powered': bool(blob[7] & 0x40),
              'remote_wakeup': bool(blob[7] & 0x20),
              'max_power_ma': blob[8] * (8 if usb_bcd >= 0x300 else 2), 'raw': blob.hex(),
              'interfaces': [], 'extra_descriptors': []}
    offset = 9
    interface = None
    seen_interfaces = set()
    while offset < len(blob):
        if len(blob) - offset < 2:
            raise DescriptorError('truncated descriptor header')
        size, kind = blob[offset:offset + 2]
        if size < 2 or size > len(blob) - offset or kind == 2:
            raise DescriptorError('invalid nested descriptor length/type')
        chunk = blob[offset:offset + size]
        if kind == 4:
            if size < 9:
                raise DescriptorError('short interface descriptor')
            key = chunk[2], chunk[3]
            if key in seen_interfaces:
                raise DescriptorError('duplicate interface/alternate pair')
            seen_interfaces.add(key)
            interface = {'number': chunk[2], 'alternate': chunk[3], 'endpoint_count': chunk[4],
                         'class': chunk[5], 'subclass': chunk[6], 'protocol': chunk[7],
                         'string_index': chunk[8], 'endpoints': [],
                         'usbmux_compatible': chunk[5:8] == bytes((255, 254, 2))}
            result['interfaces'].append(interface)
        elif kind == 5:
            if size < 7 or interface is None or not chunk[2] & 15 or chunk[2] & 0x70:
                raise DescriptorError('invalid endpoint descriptor or missing interface')
            if any(ep['address'] == chunk[2] for ep in interface['endpoints']):
                raise DescriptorError('duplicate endpoint address in alternate setting')
            interface['endpoints'].append({'address': chunk[2],
                'direction': 'in' if chunk[2] & 0x80 else 'out', 'attributes': chunk[3],
                'transfer_type': chunk[3] & 3, 'max_packet_size_raw': le16(chunk, 4),
                'max_packet_size': le16(chunk, 4) & 0x7ff, 'interval': chunk[6]})
        else:
            result['extra_descriptors'].append({'type': kind, 'length': size, 'raw': chunk.hex()})
        offset += size
    if len({item['number'] for item in result['interfaces']}) != result['interface_count']:
        raise DescriptorError('interface count mismatch')
    for item in result['interfaces']:
        if len(item['endpoints']) != item['endpoint_count']:
            raise DescriptorError('endpoint count mismatch')
    return result


def cached_descriptors(blob):
    """Linux sysfs 'descriptors' contains a device followed by configurations."""
    if len(blob) > 1024 * 1024:
        raise DescriptorError('cached descriptor size limit')
    device = device_descriptor(blob[:18])
    configurations = []
    offset = 18
    for _ in range(device['configurations']):
        if len(blob) - offset < 9:
            raise DescriptorError('missing cached configuration')
        size = le16(blob, offset + 2)
        if size < 9 or size > len(blob) - offset:
            raise DescriptorError('truncated cached configuration')
        configurations.append(configuration_descriptor(blob[offset:offset + size], device['usb_bcd']))
        offset += size
    if offset != len(blob):
        raise DescriptorError('unexpected cached descriptor tail')
    return {'device_descriptor': device, 'configurations': configurations}


def string_descriptor(blob):
    if len(blob) < 2 or blob[1] != 3 or blob[0] < 2 or blob[0] > len(blob) or blob[0] % 2:
        raise DescriptorError('invalid string descriptor')
    return blob[2:blob[0]].decode('utf-16-le', errors='replace')
