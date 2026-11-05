// SPDX-License-Identifier: MIT
#include "descriptors.h"
#include <string.h>
unsigned diag_le16(const uint8_t *p) { return (unsigned)p[0] | ((unsigned)p[1] << 8); }
dt_status diag_validate_device(const uint8_t *b, size_t n) {
    if (!b || n != 18 || b[0] != 18 || b[1] != 1 || !b[17])
        return DT_ERROR_PROTOCOL;
    return DT_OK;
}
dt_status diag_validate_config(const uint8_t *b, size_t n) {
    size_t off = 0;
    int have_interface = 0;
    uint8_t pairs[256][32] = {{0}}, numbers[256] = {0};
    unsigned unique = 0, endpoints = 0, expected = 0;
    uint32_t endpoint_mask = 0;
    if (!b || n < 9 || b[0] != 9 || b[1] != 2 || diag_le16(b + 2) != n || !b[5] || !(b[7] & 0x80))
        return DT_ERROR_PROTOCOL;
    while (off < n) {
        if (n - off < 2)
            return DT_ERROR_PROTOCOL;
        unsigned len = b[off], type = b[off + 1];
        if (len < 2 || len > n - off || (off && type == 2))
            return DT_ERROR_PROTOCOL;
        if (type == 4) {
            if (len < 9)
                return DT_ERROR_PROTOCOL;
            if (have_interface && endpoints != expected)
                return DT_ERROR_PROTOCOL;
            unsigned number = b[off + 2], alt = b[off + 3];
            uint8_t mask = (uint8_t)(1u << (alt & 7));
            if (pairs[number][alt >> 3] & mask)
                return DT_ERROR_PROTOCOL;
            pairs[number][alt >> 3] |= mask;
            if (!numbers[number]) {
                numbers[number] = 1;
                unique++;
            }
            have_interface = 1;
            endpoints = 0;
            expected = b[off + 4];
            endpoint_mask = 0;
        } else if (type == 5) {
            if (len < 7 || !have_interface || !(b[off + 2] & 15) || (b[off + 2] & 0x70))
                return DT_ERROR_PROTOCOL;
            unsigned bit = (b[off + 2] & 15u) + ((b[off + 2] & 0x80u) ? 16u : 0u);
            if (endpoint_mask & (1u << bit))
                return DT_ERROR_PROTOCOL;
            endpoint_mask |= 1u << bit;
            endpoints++;
        }
        off += len;
    }
    return unique != b[4] || (have_interface && endpoints != expected) ? DT_ERROR_PROTOCOL : DT_OK;
}
dt_status diag_validate_string(const uint8_t *b, size_t n) {
    return !b || n < 2 || b[1] != 3 || b[0] < 2 || b[0] > n || (b[0] & 1) ? DT_ERROR_PROTOCOL
                                                                          : DT_OK;
}
