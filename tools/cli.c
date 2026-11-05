// SPDX-License-Identifier: MIT
#include "diagnostics/descriptors.h"
#include "diagnostics/device_db.h"
#include "dwc2_transport/transport.h"
#include "hostlab/hl_clock.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/utsname.h>
#include <unistd.h>
static void string(const char *s) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        if (*p == '"' || *p == '\\')
            printf("\\%c", *p);
        else if (*p < 32 || *p >= 127)
            printf("\\u%04x", *p);
        else
            putchar(*p);
    }
    putchar('"');
}
static void hex(const uint8_t *p, size_t n) {
    putchar('"');
    for (size_t i = 0; i < n; i++)
        printf("%02x", p[i]);
    putchar('"');
}
static unsigned le16(const uint8_t *p) { return (unsigned)p[0] | ((unsigned)p[1] << 8); }
static const char *mode(const dt_device_info *d) {
    const struct diag_identity *identity = diag_identify(d->vendor_id, d->product_id);
    return identity ? identity->mode : d->vendor_id == 0x05ac ? "apple_unknown" : "not_apple";
}
static void device_json(const dt_device_info *d) {
    printf("{\"bus\":%u,\"address\":%u,\"vendor_id\":%u,\"product_id\":%u,"
           "\"class\":%u,\"speed\":",
           d->bus, d->address, d->vendor_id, d->product_id, d->device_class);
    string(dt_speed_name(d->speed));
    printf(",\"path\":");
    string(d->path);
    printf(",\"driver\":");
    string(d->driver);
    printf(",\"controller\":");
    string(d->controller);
    printf(",\"usb_mode\":");
    string(mode(d));
    printf(",\"sysfs_name\":");
    string(d->sysfs_name);
    printf(",\"port_count\":%u,\"ports\":[", d->port_count);
    for (unsigned i = 0; i < d->port_count && i < 7; i++) {
        if (i)
            putchar(',');
        printf("%u", d->ports[i]);
    }
    printf("],\"identification\":{\"database_version\":");
    string(DIAG_DB_VERSION);
    const struct diag_identity *id = diag_identify(d->vendor_id, d->product_id);
    printf(",\"label\":");
    string(id ? id->label : "Unknown USB identity");
    printf(",\"confidence\":");
    string(id ? id->confidence : "unknown");
    printf(",\"identity_category\":");
    string(id ? id->category : "unknown");
    printf(",\"state_category\":");
    string(id ? id->state_category : "unknown");
    printf(",\"state_verified\":false,\"evidence_basis\":");
    string(id ? "public_project_documentation" : "unclassified_observation");
    printf(",\"model\":\"unverified\",\"model_verified\":false,\"caveat\":");
    string(id ? id->caveat : "No mode or model claim can be made from this identifier.");
    printf(",\"source_urls\":");
    fputs(id ? id->sources : "[]", stdout);
    printf("}}");
}
static void device_text(const dt_device_info *d) {
    printf("%03u:%03u %04x:%04x speed=%s class=%02x driver=%s controller=%s %s "
           "(%s)\n",
           d->bus, d->address, d->vendor_id, d->product_id, dt_speed_name(d->speed),
           d->device_class, d->driver, d->controller, d->path, mode(d));
}
static int matches(const dt_device_info *d, const char *locator) {
    unsigned v, p;
    char tail;
    if (!strcmp(d->path, locator))
        return 1;
    return strlen(locator) == 9 && sscanf(locator, "%4x:%4x%c", &v, &p, &tail) == 2 &&
           d->vendor_id == v && d->product_id == p;
}
static void error_json(const dt_error *e) {
    printf("{\"schema\":1,\"error\":{\"status\":");
    string(dt_status_name(e->status));
    printf(",\"errno\":%d,\"operation\":", e->system_errno);
    string(e->operation);
    printf(",\"message\":");
    string(e->message);
    puts("}}");
}
static int descriptor_walk(const uint8_t *b, size_t n, int json) {
    size_t off = 0;
    unsigned item = 0;
    if (diag_validate_config(b, n) != DT_OK)
        return -1;
    if (json)
        printf("[");
    while (off < n) {
        unsigned len = b[off], type;
        if (len < 2 || len > n - off)
            return -1;
        type = b[off + 1];
        if ((type == 4 && len < 9) || (type == 5 && len < 7))
            return -1;
        if (json) {
            if (item++)
                putchar(',');
            printf("{\"type\":%u,\"length\":%u", type, len);
        }
        if (type == 4) {
            if (json)
                printf(
                    ",\"interface\":%u,\"alternate\":%u,\"endpoints\":%u,\"class\":%u,\"subclass\":"
                    "%u,\"protocol\":%u,\"string_index\":%u,\"usbmux_compatible\":%s",
                    b[off + 2], b[off + 3], b[off + 4], b[off + 5], b[off + 6], b[off + 7],
                    b[off + 8],
                    b[off + 5] == 255 && b[off + 6] == 254 && b[off + 7] == 2 ? "true" : "false");
            else
                printf("  interface %u alternate %u class %02x endpoints %u\n", b[off + 2],
                       b[off + 3], b[off + 5], b[off + 4]);
        } else if (type == 5) {
            if (json)
                printf(",\"endpoint\":%u,\"attributes\":%u,\"max_packet_size\":%u,"
                       "\"interval\":%u,\"direction\":\"%s\",\"transfer_type\":%u",
                       b[off + 2], b[off + 3], le16(b + off + 4), b[off + 6],
                       b[off + 2] & 0x80 ? "in" : "out", b[off + 3] & 3);
            else
                printf("    endpoint 0x%02x attributes %u packet %u interval %u\n", b[off + 2],
                       b[off + 3], le16(b + off + 4), b[off + 6]);
        }
        if (json)
            putchar('}');
        off += len;
    }
    if (json)
        printf("]");
    return 0;
}
/* Render UTF-16LE directly as JSON escapes, replacing invalid surrogate units.
 */
static void usb_string_json(const uint8_t *b, size_t n) {
    putchar('"');
    for (size_t i = 2; i + 1 < n; i += 2) {
        unsigned u = le16(b + i);
        if (u >= 0xd800 && u <= 0xdbff) {
            if (i + 3 < n) {
                unsigned v = le16(b + i + 2);
                if (v >= 0xdc00 && v <= 0xdfff) {
                    printf("\\u%04x\\u%04x", u, v);
                    i += 2;
                    continue;
                }
            }
            u = 0xfffd;
        } else if (u >= 0xdc00 && u <= 0xdfff)
            u = 0xfffd;
        printf("\\u%04x", u);
    }
    putchar('"');
}
static int inspect(dt_device *d, int json, int include_serial) {
    uint8_t dev[18], head[9], str[255];
    size_t n = 0;
    dt_error e;
    int rc = 0;
    unsigned lang = 0, roles[256] = {0};
    dt_status status = dt_get_descriptor(d, 1, 0, 0, dev, 18, &n, &e);
    if (!status)
        status = diag_validate_device(dev, n);
    if (status) {
        if (!e.status) {
            e.status = status;
            snprintf(e.operation, sizeof(e.operation), "device_descriptor");
            snprintf(e.message, sizeof(e.message), "short or invalid device descriptor");
        }
        if (json)
            error_json(&e);
        else
            fprintf(stderr, "%s: %s\n", e.operation, e.message);
        return 1;
    }
    for (unsigned k = 14; k <= 16; k++)
        if (dev[k])
            roles[dev[k]] |= 1u << (k - 14);
    if (json) {
        printf("{\"schema\":1,\"diagnostic_schema\":2,\"serial_policy\":");
        string(include_serial ? "explicitly_included" : "redacted");
        printf(",\"device\":");
        device_json(dt_device_get_info(d));
        printf(
            ",\"device_descriptor\":{\"usb_bcd\":%u,\"class\":%u,\"subclass\":%u,\"protocol\":%u,"
            "\"max_packet_size0\":%u,\"device_bcd\":%u,\"manufacturer_index\":%u,\"product_index\":"
            "%u,"
            "\"serial_index\":%u,\"configurations\":%u,\"raw\":",
            le16(dev + 2), dev[4], dev[5], dev[6], dev[7], le16(dev + 12), dev[14], dev[15],
            dev[16], dev[17]);
        hex(dev, 18);
        printf("},\"configurations\":[");
    } else {
        device_text(dt_device_get_info(d));
        printf("device USB %04x class %02x ep0 packet %u configurations %u; serial %s\n",
               le16(dev + 2), dev[4], dev[7], dev[17],
               include_serial ? "explicitly included" : "redacted");
    }
    unsigned count = dev[17] > 16 ? 16 : dev[17];
    for (unsigned i = 0; i < count; i++) {
        uint8_t *b = NULL;
        size_t len = 0;
        status = dt_get_descriptor(d, 2, (uint8_t)i, 0, head, 9, &n, &e);
        if (!status && (n != 9 || head[0] != 9 || head[1] != 2))
            status = DT_ERROR_PROTOCOL;
        if (!status) {
            len = le16(head + 2);
            if (len < 9 || len > DT_MAX_CONTROL_LENGTH)
                status = DT_ERROR_UNSUPPORTED;
        }
        if (!status) {
            b = malloc(len);
            if (!b)
                status = DT_ERROR_NOMEM;
        }
        if (!status)
            status = dt_get_descriptor(d, 2, (uint8_t)i, 0, b, (uint16_t)len, &n, &e);
        if (!status)
            status = diag_validate_config(b, n);
        if (!status && n != len)
            status = DT_ERROR_PROTOCOL;
        if (!status) {
            if (b[6])
                roles[b[6]] |= 8;
            for (size_t off = 9; off < n; off += b[off])
                if (b[off + 1] == 4 && b[off + 8])
                    roles[b[off + 8]] |= 16;
        }
        if (json) {
            if (i)
                putchar(',');
            printf("{\"index\":%u,\"status\":", i);
            string(dt_status_name(status));
            if (!status) {
                printf(",\"value\":%u,\"interface_count\":%u,\"attributes\":%u,\"self_powered\":%s,"
                       "\"remote_wakeup\":%s,\"max_power_ma\":%u,\"raw\":",
                       b[5], b[4], b[7], b[7] & 0x40 ? "true" : "false",
                       b[7] & 0x20 ? "true" : "false", b[8] * (le16(dev + 2) >= 0x0300 ? 8u : 2u));
                hex(b, n);
                printf(",\"descriptors\":");
                (void)descriptor_walk(b, n, 1);
            } else
                printf(",\"errno\":%d", e.status == status ? e.system_errno : 0);
            printf("}");
        } else {
            printf("configuration %u: %s\n", i, dt_status_name(status));
            if (!status)
                (void)descriptor_walk(b, n, 0);
        }
        if (status)
            rc = 1;
        free(b);
    }
    dt_status language_status = dt_get_descriptor(d, 3, 0, 0, str, sizeof(str), &n, &e);
    if (!language_status && diag_validate_string(str, n) == DT_OK && str[0] >= 4)
        lang = le16(str + 2);
    if (json)
        printf("],\"configuration_limit_reached\":%s,\"string_language\":%u,\"strings\":[",
               dev[17] > count ? "true" : "false", lang);
    unsigned emitted = 0, requested = 0;
    for (unsigned index = 1; index < 256; index++) {
        if (!roles[index])
            continue;
        if (json) {
            if (emitted++)
                putchar(',');
            printf("{\"index\":%u,\"roles_mask\":%u,\"status\":", index, roles[index]);
        }
        if (index == dev[16] && !include_serial) {
            if (json)
                printf("\"redacted\",\"redacted\":true}");
            else
                printf("string %u: [serial redacted]\n", index);
            continue; /* Never request the serial, including indices shared with other roles. */
        }
        if (requested++ >= 32)
            status = DT_ERROR_UNSUPPORTED;
        else
            status = lang ? dt_get_descriptor(d, 3, (uint8_t)index, (uint16_t)lang, str,
                                              sizeof(str), &n, &e)
                     : language_status ? language_status
                                       : DT_ERROR_PROTOCOL;
        if (!status)
            status = diag_validate_string(str, n);
        if (!status)
            n = str[0];
        if (json) {
            string(dt_status_name(status));
            if (!status) {
                printf(",\"raw\":");
                hex(str, n);
                printf(",\"text\":");
                usb_string_json(str, n);
            }
            printf("}");
        } else {
            printf("string %u: %s", index, dt_status_name(status));
            if (!status) {
                printf(" ");
                usb_string_json(str, n);
            }
            puts("");
        }
    }
    if (json)
        puts("]}");
    return dev[17] > count ? 1 : rc;
}
static void platform_json(void) {
    struct utsname u;
    char model[128] = "unknown";
    FILE *f = fopen("/proc/device-tree/model", "rb");
    if (f) {
        size_t n = fread(model, 1, sizeof(model) - 1, f);
        model[n] = 0;
        fclose(f);
    }
    memset(&u, 0, sizeof(u));
    (void)uname(&u);
    printf("\"platform\":{\"system\":");
    string(u.sysname);
    printf(",\"kernel\":");
    string(u.release);
    printf(",\"machine\":");
    string(u.machine);
    printf(",\"model\":");
    string(model);
    printf(",\"usbmon_accessible\":%s,\"tracefs_accessible\":%s,\"kprobes_"
           "accessible\":%s}",
           access("/dev/usbmon0", R_OK) == 0 ? "true" : "false",
           access("/sys/kernel/tracing/trace", R_OK) == 0 ? "true" : "false",
           access("/sys/kernel/tracing/kprobe_events", R_OK) == 0 ? "true" : "false");
}
static void emit_xfer(struct hl_jsonl *j, const dt_completion *r, unsigned seq) {
    hl_jsonl_begin(j);
    hl_jsonl_str(j, "src", "user");
    hl_jsonl_str(j, "ev", "xfer");
    hl_jsonl_str(j, "op", "control_async");
    hl_jsonl_u64(j, "seq", seq);
    hl_jsonl_str(j, "setup", "8006000100001200");
    hl_jsonl_u64(j, "t_submit_ns", r->submitted_ns);
    hl_jsonl_u64(j, "t_reap_ns", r->reaped_ns);
    hl_jsonl_u64(j, "t_done_ns", r->reaped_ns);
    hl_jsonl_str(j, "status", dt_status_name(r->status));
    hl_jsonl_i64(j, "urb_status", r->kernel_status);
    hl_jsonl_u64(j, "actual", r->actual_length);
    hl_jsonl_end(j);
}
static int diagnostics(dt_context *c, dt_device *d, int json, int jsonl, unsigned repeat) {
    unsigned ok = 0, errors = 0, timeouts = 0, cancelled = 0;
    dt_error e;
    struct hl_jsonl j;
    if (jsonl) {
        hl_jsonl_init(&j, stdout);
        hl_jsonl_begin(&j);
        hl_jsonl_str(&j, "src", "user");
        hl_jsonl_str(&j, "ev", "meta");
        hl_jsonl_str(&j, "tool", "usb-diagnostics");
        hl_jsonl_str(&j, "version", dt_version());
        hl_jsonl_u64(&j, "schema", 1);
        hl_jsonl_str(&j, "backend", dt_backend_name(c));
        hl_jsonl_end(&j);
        if (!(d && dt_capabilities(d) & DT_CAP_VIRTUAL_CLOCK)) {
            struct hl_clock_snap s;
            hl_clock_snapshot(&s);
            hl_clock_emit(&j, "user", &s);
        }
    }
    for (unsigned i = 0; d && i < repeat; i++) {
        dt_setup setup = {0x80, 6, 0x100, 0, 18};
        dt_transfer *x = NULL, *done = NULL;
        if (dt_submit_control(d, &setup, NULL, 1000, NULL, &x, &e) || dt_reap(d, 1500, &done, &e)) {
            errors++;
            if (jsonl) {
                hl_jsonl_begin(&j);
                hl_jsonl_str(&j, "ev", "error");
                hl_jsonl_str(&j, "status", dt_status_name(e.status));
                hl_jsonl_end(&j);
            }
            continue;
        }
        const dt_completion *r = dt_transfer_result(done);
        if (r->status == DT_OK && r->actual_length == 18)
            ok++;
        else
            errors++;
        if (r->status == DT_ERROR_TIMEOUT)
            timeouts++;
        if (r->status == DT_ERROR_CANCELLED)
            cancelled++;
        if (jsonl)
            emit_xfer(&j, r, i);
        (void)dt_transfer_free(done, NULL);
    }
    if (jsonl) {
        hl_jsonl_begin(&j);
        hl_jsonl_str(&j, "ev", "summary");
        hl_jsonl_u64(&j, "ok", ok);
        hl_jsonl_u64(&j, "errors", errors);
        hl_jsonl_end(&j);
    } else if (json) {
        printf("{\"schema\":1,\"sdk_version\":");
        string(dt_version());
        printf(",\"backend\":");
        string(dt_backend_name(c));
        printf(",");
        platform_json();
        printf(",\"sdk_api\":%u,\"sdk_features\":{\"control\":true,\"async_control\":true,"
               "\"cancel\":true,\"reset\":true,\"claim\":true,\"async_endpoint\":true},"
               "\"capabilities\":%u,\"device\":",
               dt_api_version(), dt_capabilities(d));
        if (d)
            device_json(dt_device_get_info(d));
        else
            printf("null");
        printf(",\"transfers\":{\"requested\":%u,\"ok\":%u,\"errors\":%u,"
               "\"timeouts\":%u,\"cancelled\":%u}}\n",
               d ? repeat : 0, ok, errors, timeouts, cancelled);
    } else {
        struct utsname u;
        memset(&u, 0, sizeof(u));
        (void)uname(&u);
        printf("SDK %s backend %s | %s %s %s\n", dt_version(), dt_backend_name(c), u.sysname,
               u.release, u.machine);
        printf("tracing accessible: usbmon=%s tracefs=%s kprobes=%s\n",
               access("/dev/usbmon0", R_OK) == 0 ? "yes" : "no",
               access("/sys/kernel/tracing/trace", R_OK) == 0 ? "yes" : "no",
               access("/sys/kernel/tracing/kprobe_events", R_OK) == 0 ? "yes" : "no");
        if (d)
            device_text(dt_device_get_info(d));
        printf("capabilities=0x%x transfers ok=%u errors=%u timeouts=%u "
               "cancelled=%u\n",
               dt_capabilities(d), ok, errors, timeouts, cancelled);
    }
    return errors ? 1 : 0;
}
int main(int argc, char **argv) {
    const char *tool = strrchr(argv[0], '/');
    tool = tool ? tool + 1 : argv[0];
    const char *backend = "linux-usbfs", *locator = NULL, *profile = "generic";
    int json = 0, jsonl = 0, apple = 0, rc = 1, include_serial = 0;
    unsigned repeat = 10;
    dt_context *c = NULL;
    dt_device *d = NULL;
    dt_device_info *list = NULL;
    size_t count = 0;
    dt_error e;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--mock"))
            backend = "mock";
        else if (!strcmp(argv[i], "--include-serial"))
            include_serial = 1;
        else if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--jsonl"))
            jsonl = 1;
        else if (!strcmp(argv[i], "--device") && i + 1 < argc)
            locator = argv[++i];
        else if (!strcmp(argv[i], "--profile") && i + 1 < argc)
            profile = argv[++i];
        else if (!strcmp(argv[i], "--repeat") && i + 1 < argc) {
            char *end;
            unsigned long n = strtoul(argv[++i], &end, 10);
            if (*end || !n || n > 1000)
                goto usage;
            repeat = (unsigned)n;
        } else if (!strcmp(argv[i], "--version")) {
            puts(dt_version());
            return 0;
        } else if (!strcmp(argv[i], "--help")) {
            rc = 0;
            goto usage;
        } else
            goto usage;
    }
    apple = !strcmp(profile, "apple-tv-a1427");
    if (strcmp(profile, "generic") && !apple)
        goto usage;
    if (jsonl && (strcmp(tool, "usb-diagnostics") || json))
        goto usage;
    if (dt_context_create(backend, &c, &e) || dt_enumerate(c, &list, &count, &e))
        goto failure;
    if (!strcmp(tool, "usb-discover")) {
        if (json) {
            printf("{\"schema\":1,\"sdk_version\":");
            string(dt_version());
            printf(",\"backend\":");
            string(backend);
            printf(",\"profile\":");
            string(profile);
            printf(",\"devices\":[");
        }
        unsigned emitted = 0;
        for (size_t i = 0; i < count; i++) {
            if ((apple && list[i].vendor_id != 0x05ac) || (locator && !matches(&list[i], locator)))
                continue;
            if (json) {
                if (emitted++)
                    putchar(',');
                device_json(&list[i]);
            } else
                device_text(&list[i]);
        }
        if (json)
            puts("]}");
        rc = 0;
        goto done;
    }
    if (locator || !strcmp(tool, "usb-inspect")) {
        const dt_device_info *selected = NULL;
        for (size_t i = 0; i < count; i++) {
            if (apple && list[i].vendor_id != 0x05ac)
                continue;
            if (locator ? matches(&list[i], locator) : !strcmp(backend, "mock")) {
                if (selected) {
                    e = (dt_error){.status = DT_ERROR_INVALID,
                                   .operation = "select",
                                   .message = "multiple matches; select exact device path"};
                    goto failure;
                }
                selected = &list[i];
            }
        }
        if (!selected) {
            e = (dt_error){.status = DT_ERROR_NO_DEVICE,
                           .operation = "select",
                           .message = "no match; specify --device path or VID:PID"};
            goto failure;
        }
        if (selected->device_class == 9) {
            e = (dt_error){.status = DT_ERROR_ACCESS,
                           .operation = "select",
                           .message = "diagnostics refuses hub transfers"};
            goto failure;
        }
        if (dt_open(c, selected, &d, &e))
            goto failure;
    }
    rc = !strcmp(tool, "usb-inspect") ? inspect(d, json, include_serial)
                                      : diagnostics(c, d, json, jsonl, repeat);
    goto done;
failure:
    if (json || jsonl)
        error_json(&e);
    else
        fprintf(stderr, "%s: %s (%s, errno %d)\n", e.operation, e.message, dt_status_name(e.status),
                e.system_errno);
    goto done;
usage:
    fprintf(rc ? stderr : stdout,
            "usage: %s [--mock] [--device PATH|VID:PID] [--json|--jsonl] "
            "[--repeat 1..1000] [--profile apple-tv-a1427] [--include-serial]\n",
            tool);
    if (rc)
        rc = 2;
done:
    dt_close(d);
    dt_device_list_free(list);
    dt_context_destroy(c);
    return rc;
}
