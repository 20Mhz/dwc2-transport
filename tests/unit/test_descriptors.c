// SPDX-License-Identifier: MIT
#include "../../tools/diagnostics/descriptors.h"
#include "../../tools/diagnostics/device_db.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define C(x)                                                                                       \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "line %d: %s\n", __LINE__, #x);                                        \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
int main(void) {
    uint8_t device[18] = {18, 1, 0, 2, 0, 0, 0, 64, 0xac, 5, 0xa7, 0x12, 0x10, 3, 1, 2, 3, 1};
    uint8_t config[32] = {9, 2, 32, 0, 1, 1, 0, 0x80, 50, 9, 4, 0,    0, 2, 0xff, 0xfe,
                          2, 0, 7,  5, 2, 2, 0, 2,    0,  7, 5, 0x81, 2, 0, 2,    0};
    C(diag_validate_device(device, 18) == DT_OK);
    for (size_t n = 0; n < 18; n++)
        C(diag_validate_device(device, n) != DT_OK);
    C(diag_validate_config(config, sizeof(config)) == DT_OK);
    for (size_t n = 0; n < sizeof(config); n++)
        C(diag_validate_config(config, n) != DT_OK);
    config[9] = 0;
    C(diag_validate_config(config, 32) != DT_OK);
    config[9] = 9;
    config[10] = 5;
    C(diag_validate_config(config, 32) != DT_OK);
    config[10] = 4;
    config[20] = 0x80;
    C(diag_validate_config(config, 32) != DT_OK);
    config[20] = 2;
    config[13] = 3;
    C(diag_validate_config(config, 32) != DT_OK);
    config[13] = 2;
    config[4] = 2;
    C(diag_validate_config(config, 32) != DT_OK);
    config[4] = 1;
    config[27] = 2;
    C(diag_validate_config(config, 32) != DT_OK);
    config[27] = 0x81;
    uint8_t odd[] = {3, 3, 0};
    C(diag_validate_string(odd, 3) != DT_OK);
    uint8_t text[] = {4, 3, 'A', 0};
    C(diag_validate_string(text, 4) == DT_OK);
    C(diag_validate_string(text, 3) != DT_OK);
    C(diag_validate_config(NULL, 32) != DT_OK);
    C(diag_validate_string(NULL, 0) != DT_OK);
    const struct diag_identity *id = diag_identify(0x05ac, 0x12a7);
    C(id && !strcmp(id->mode, "apple_tv_usb") && !strcmp(id->model, "unverified"));
    C(!diag_identify(0x05ac, 0xffff));
    C(!diag_identify(0x1234, 0x1227));
    C(!strcmp(diag_identify(0x05ac, 0x1227)->mode, "dfu"));
    C(!strcmp(diag_identify(0x05ac, 0x1281)->mode, "recovery"));
    puts("diagnostic parsers and known/unknown identities PASS");
    return 0;
}
