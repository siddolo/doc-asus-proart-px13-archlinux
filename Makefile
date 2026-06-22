PYTHON ?= python3
MAKEFLAGS += --no-builtin-rules

.SUFFIXES:

EXPORT_DIR := exports
GENERATOR := tools/generate-mediawiki.py
MARKDOWN_SOURCES := $(shell find . -type f -name '*.md' ! -path './.git/*' ! -path './.obsidian/*' ! -path './configs/*' ! -path './exports/*' ! -path './to-do/*' ! -path './tools/*' ! -name 'AGENTS.md' -printf '%P\n' | sort)
WIKI_TARGETS := $(shell set -e; for source in $(MARKDOWN_SOURCES); do $(PYTHON) $(GENERATOR) --target-for "$$source"; done)

.PHONY: all wiki check clean list

all: wiki

wiki:
	@set -e; \
	for source in $(MARKDOWN_SOURCES); do \
		$(PYTHON) $(GENERATOR) "$$source"; \
	done

check:
	@set -e; \
	for source in $(MARKDOWN_SOURCES); do \
		$(PYTHON) $(GENERATOR) --check "$$source"; \
	done

clean:
	@if [ -d "$(EXPORT_DIR)" ]; then find "$(EXPORT_DIR)" -type f -name '*.wiki' -delete; fi

list:
	@printf '%s\n' $(MARKDOWN_SOURCES)
