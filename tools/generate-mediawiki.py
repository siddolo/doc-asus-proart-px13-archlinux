#!/usr/bin/env python3
"""Generate MediaWiki export from installazione-base-arch-linux.md.

This is a small, intentionally limited Markdown-to-MediaWiki converter for the
format used by this repository's installation documents. Markdown remains the
single source of truth.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "installazione-base-arch-linux.md"
DEFAULT_TARGET = ROOT / "exports" / "installazione-base-arch-linux.wiki"


def fence_language(markdown_language: str) -> str:
    language = markdown_language.strip().lower()
    if language in {"sh", "shell"}:
        return "bash"
    return language or "text"


def convert_inline_code(text: str) -> str:
    parts = text.split("`")
    if len(parts) == 1:
        return text

    converted: list[str] = []
    in_code = False
    for part in parts:
        if in_code:
            converted.append(f"<code>{html.escape(part, quote=False)}</code>")
        else:
            converted.append(part)
        in_code = not in_code

    return "".join(converted)


def convert_line(line: str) -> str:
    heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if heading:
        level = len(heading.group(1))
        marker = "=" * level
        title = re.sub(r"^\d+(?:\.\d+)*\.\s+", "", heading.group(2))
        title = convert_inline_code(title)
        return f"{marker} {title} {marker}"

    bullet = re.match(r"^(\s*)[-*]\s+(.+)$", line)
    if bullet:
        indent = len(bullet.group(1).replace("\t", "  "))
        level = indent // 2 + 1
        return f"{'*' * level} {convert_inline_code(bullet.group(2))}"

    return convert_inline_code(line)


def convert_markdown(markdown: str) -> str:
    output: list[str] = []
    in_fence = False

    for line in markdown.splitlines():
        fence = re.match(r"^```\s*([^`]*)$", line)
        if fence:
            if in_fence:
                output.append("</syntaxhighlight>")
                in_fence = False
            else:
                output.append(f'<syntaxhighlight lang="{fence_language(fence.group(1))}">')
                in_fence = True
            continue

        if in_fence:
            output.append(line)
            continue

        output.append(convert_line(line))

    if in_fence:
        raise ValueError("unterminated Markdown code fence")

    return "\n".join(output) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MediaWiki markup from Markdown")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("target", nargs="?", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true", help="fail if the target is not up to date")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source
    target = args.target

    try:
        generated = convert_markdown(source.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"error reading {source}: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"error converting {source}: {error}", file=sys.stderr)
        return 1

    if args.check:
        try:
            current = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"{target} does not exist", file=sys.stderr)
            return 1
        except OSError as error:
            print(f"error reading {target}: {error}", file=sys.stderr)
            return 1

        if current != generated:
            print(f"{target} is not up to date; run {Path(__file__).name}", file=sys.stderr)
            return 1

        return 0

    try:
        target.write_text(generated, encoding="utf-8")
    except OSError as error:
        print(f"error writing {target}: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
