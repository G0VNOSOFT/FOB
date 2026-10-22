# FOB — 0xF4CK 0xFF B1NʎRY
FASM     ?= fasm
PYTHON   ?= python3
PREFIX   ?= /usr/local
BUILD    := build
FOB_BIN  := bin/fob
FOBC     := tools/fobc.py
SRC      := src/fob.asm

TESTS    := hello countdown sanity stack sum factorial syswrite csum_ok jcc ptr strl
NATIVE   := $(addprefix $(BUILD)/native/,$(TESTS))
HEADER_OK:= $(BUILD)/.header_ok

.PHONY: all build test native install clean help

all: build

build: $(FOB_BIN) $(FOBC)
	@echo "[build] done"

$(FOB_BIN): $(SRC)
	@mkdir -p bin
	$(FASM) $(SRC) $(FOB_BIN)
	@chmod +x $(FOB_BIN)

$(FOBC):
	@echo "[error] missing $(FOBC)"; exit 1

native: $(NATIVE)
	@echo "[native] done"

$(BUILD)/native/%: tests/%.fob $(FOBC) $(FOB_BIN)
	@mkdir -p $(BUILD)/native
	@$(PYTHON) $(FOBC) $< $@
	@chmod +x $@

test: build native
	@bash tests/run_tests.sh

install: build
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 0755 $(FOB_BIN) $(DESTDIR)$(PREFIX)/bin/fob
	install -m 0755 $(FOBC)    $(DESTDIR)$(PREFIX)/bin/fobc
	@echo "[install] fob, fobc → $(PREFIX)/bin"

clean:
	rm -rf $(BUILD) bin/native

help:
	@echo "targets:"
	@echo "  build   — compile fob interpreter (bin/fob)"
	@echo "  native  — compile all tests to native binaries"
	@echo "  test    — run tests/run_tests.sh (needs fasm on PATH)"
	@echo "  install — install fob and fobc to \$$PREFIX/bin"
	@echo "  clean   — remove build artifacts"
