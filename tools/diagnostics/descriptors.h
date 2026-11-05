/* SPDX-License-Identifier: MIT; private diagnostic parser, not SDK ABI. */
#ifndef DIAG_DESCRIPTORS_H
#define DIAG_DESCRIPTORS_H
#include "dwc2_transport/errors.h"
#include <stddef.h>
#include <stdint.h>
unsigned diag_le16(const uint8_t *p);
dt_status diag_validate_device(const uint8_t *b, size_t n);
dt_status diag_validate_config(const uint8_t *b, size_t n);
dt_status diag_validate_string(const uint8_t *b, size_t n);
#endif
