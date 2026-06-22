PYTHON ?= python3
MAKEFLAGS += --no-builtin-rules

.SUFFIXES:

EXPORT_DIR := exports
GENERATOR := tools/generate-mediawiki.py
MARKDOWN_SOURCES := $(shell find . -type f -name '*.md' ! -path './.git/*' ! -path './.obsidian/*' ! -path './configs/*' ! -path './exports/*' ! -path './to-do/*' ! -path './tools/*' ! -name 'AGENTS.md' -printf '%P\n' | sort)
WIKI_TARGETS := $(patsubst %.md,$(EXPORT_DIR)/%.wiki,$(MARKDOWN_SOURCES))

.PHONY: all wiki check clean list

all: wiki

wiki: $(WIKI_TARGETS)

$(EXPORT_DIR)/%.wiki: %.md $(GENERATOR)
	@mkdir -p "$(@D)"
	$(PYTHON) $(GENERATOR) "$<" "$@"

check:
	@set -e; \
	for source in $(MARKDOWN_SOURCES); do \
		target="$(EXPORT_DIR)/$${source%.md}.wiki"; \
		$(PYTHON) $(GENERATOR) --check "$$source" "$$target"; \
	done

clean:
	rm -f $(WIKI_TARGETS)

list:
	@printf '%s\n' $(MARKDOWN_SOURCES)
