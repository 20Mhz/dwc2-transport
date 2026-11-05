# Native or static ARMv6 build without external dependencies.
BUILD ?= build/native
CC ?= cc
AR ?= ar
CFLAGS ?= -O2 -g
LDFLAGS ?=
TEST_RUNNER ?=
CPPFLAGS += -D_GNU_SOURCE -Iinclude
WARN = -std=c11 -Wall -Wextra -Werror -Wshadow -Wstrict-prototypes -Wmissing-prototypes -fvisibility=hidden
SOURCES = src/common/core.c src/common/async.c src/linux/usbfs.c src/mock/mock.c
OBJS = $(SOURCES:%.c=$(BUILD)/%.o)
HEADERS = $(wildcard include/dwc2_transport/*.h src/common/*.h tools/hostlab/*.h tools/diagnostics/*.h)
PROGRAMS = usb-discover usb-inspect usb-diagnostics read-descriptor test-core test-async test-replay test-hardware test-descriptors test-inspection
.PHONY: all test clean
all: $(PROGRAMS:%=$(BUILD)/%)
$(BUILD)/%.o: %.c $(HEADERS)
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) -c $< -o $@
$(BUILD)/libdwc2_transport.a: $(OBJS) Makefile
	$(RM) $@
	$(AR) rcs $@ $(OBJS)
$(BUILD)/usb-discover $(BUILD)/usb-inspect $(BUILD)/usb-diagnostics: $(BUILD)/tools/cli.o $(BUILD)/tools/hostlab/jsonl.o $(BUILD)/tools/hostlab/clock.o $(BUILD)/tools/diagnostics/descriptors.o $(BUILD)/libdwc2_transport.a
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
$(BUILD)/read-descriptor: $(BUILD)/examples/read_descriptor.o $(BUILD)/libdwc2_transport.a
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
$(BUILD)/test-core: $(BUILD)/tests/unit/test_core.o $(BUILD)/libdwc2_transport.a
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
$(BUILD)/test-async: $(BUILD)/tests/unit/test_async.o $(BUILD)/libdwc2_transport.a
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
$(BUILD)/test-replay: $(BUILD)/tests/unit/test_replay.o $(BUILD)/libdwc2_transport.a
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
$(BUILD)/test-hardware: $(BUILD)/tests/hardware/regression.o $(BUILD)/libdwc2_transport.a
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
$(BUILD)/test-descriptors: $(BUILD)/tests/unit/test_descriptors.o $(BUILD)/tools/diagnostics/descriptors.o $(BUILD)/libdwc2_transport.a
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
$(BUILD)/tests/unit/test_inspection.o: tools/cli.c
$(BUILD)/test-inspection: $(BUILD)/tests/unit/test_inspection.o $(BUILD)/tools/diagnostics/descriptors.o $(BUILD)/tools/hostlab/jsonl.o $(BUILD)/tools/hostlab/clock.o $(BUILD)/libdwc2_transport.a
	$(CC) $(CFLAGS) $^ $(LDFLAGS) -o $@
test: all
	$(TEST_RUNNER) $(BUILD)/test-descriptors
	python3 scripts/generate-device-db.py --check
	$(TEST_RUNNER) $(BUILD)/test-core
	$(TEST_RUNNER) $(BUILD)/test-async
	$(TEST_RUNNER) $(BUILD)/test-replay tests/fixtures/hostlab-ch340.replay tests/fixtures/invalid.replay
	$(TEST_RUNNER) $(BUILD)/read-descriptor --mock
	TEST_RUNNER="$(TEST_RUNNER)" python3 tests/integration/test_cli.py $(BUILD)
	python3 tests/integration/test_apple_capture.py
	python3 tests/integration/test_observer.py
	python3 tests/integration/test_evidence.py
	python3 tests/integration/test_recording.py
	python3 tests/integration/test_timeline.py
	python3 tests/integration/test_release.py
	python3 tests/integration/test_privacy.py
clean:
	rm -rf build
