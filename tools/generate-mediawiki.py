#!/usr/bin/env python3
"""Generate MediaWiki exports from Markdown sources.

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
EXPORT_DIR = ROOT / "exports"
PUBLIC_DOC_EXCLUDES = {".git", ".obsidian", "configs", "exports", "to-do", "tools"}


def source_relative_path(source: Path) -> Path:
    source = source.resolve()
    try:
        return source.relative_to(ROOT)
    except ValueError as error:
        raise ValueError(f"{source} is outside {ROOT}") from error


def mediawiki_page_name(source: Path) -> str:
    relative = source_relative_path(source).with_suffix("")
    return "/".join(part.replace("-", "_") for part in relative.parts)


def mediawiki_target(source: Path) -> Path:
    relative = Path(*mediawiki_page_name(source).split("/"))
    return (EXPORT_DIR / relative).with_suffix(".wiki")


def markdown_sources() -> list[Path]:
    sources: list[Path] = []
    for source in ROOT.rglob("*.md"):
        relative = source.relative_to(ROOT)
        if source.name == "AGENTS.md" or any(part in PUBLIC_DOC_EXCLUDES for part in relative.parts):
            continue
        sources.append(source)
    return sorted(sources)


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


def heading_title(line: str) -> str | None:
    heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if not heading:
        return None
    return re.sub(r"^\d+(?:\.\d+)*\.\s+", "", heading.group(2))


def markdown_anchor(title: str) -> str:
    anchor = title.strip().lower()
    anchor = re.sub(r"[`*_]", "", anchor)
    anchor = re.sub(r"[^\w\s-]", "", anchor, flags=re.UNICODE)
    anchor = re.sub(r"\s+", "-", anchor)
    return anchor


def anchor_map_for(source: Path) -> dict[str, str]:
    anchors: dict[str, str] = {}
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError:
        return anchors

    for line in lines:
        title = heading_title(line)
        if title is not None:
            raw_title = re.match(r"^(#{1,6})\s+(.+?)\s*$", line).group(2)  # type: ignore[union-attr]
            converted_title = convert_inline_code(title)
            anchors[markdown_anchor(raw_title)] = converted_title
            anchors[markdown_anchor(title)] = converted_title
    return anchors


def all_anchor_maps() -> dict[Path, dict[str, str]]:
    return {source_relative_path(source): anchor_map_for(source) for source in markdown_sources()}


def markdown_link_to_mediawiki(label: str, destination: str, source: Path, anchor_maps: dict[Path, dict[str, str]]) -> str:
    if re.match(r"^[a-z][a-z0-9+.-]*:", destination) or destination.startswith("/"):
        return f"[{destination} {label}]"

    target, separator, fragment = destination.partition("#")
    if not target.endswith(".md"):
        return f"[{destination} {label}]"

    target_path = (ROOT / source_relative_path(source).parent / target).resolve()
    try:
        target_relative = target_path.relative_to(ROOT)
    except ValueError:
        return label

    page = mediawiki_page_name(ROOT / target_relative)
    if separator:
        fragment = anchor_maps.get(target_relative, {}).get(fragment, fragment.replace("-", " "))
        page = f"{page}#{fragment}"

    return f"[[{page}|{label}]]"


def convert_links(text: str, source: Path, anchor_maps: dict[Path, dict[str, str]]) -> str:
    def replace(match: re.Match[str]) -> str:
        label = match.group(1)
        destination = match.group(2).strip()
        return markdown_link_to_mediawiki(label, destination, source, anchor_maps)

    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", replace, text)


def convert_inline(text: str, source: Path, anchor_maps: dict[Path, dict[str, str]]) -> str:
    parts = text.split("`")
    if len(parts) == 1:
        return convert_links(text, source, anchor_maps)

    converted: list[str] = []
    in_code = False
    for part in parts:
        if in_code:
            converted.append(f"<code>{html.escape(part, quote=False)}</code>")
        else:
            converted.append(convert_links(part, source, anchor_maps))
        in_code = not in_code

    return "".join(converted)


def convert_line(line: str, source: Path, anchor_maps: dict[Path, dict[str, str]]) -> str:
    heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if heading:
        level = len(heading.group(1))
        marker = "=" * level
        title = heading_title(line) or heading.group(2)
        title = convert_inline(title, source, anchor_maps)
        return f"{marker} {title} {marker}"

    bullet = re.match(r"^(\s*)[-*]\s+(.+)$", line)
    if bullet:
        indent = len(bullet.group(1).replace("\t", "  "))
        level = indent // 2 + 1
        return f"{'*' * level} {convert_inline(bullet.group(2), source, anchor_maps)}"

    return convert_inline(line, source, anchor_maps)


def convert_markdown(markdown: str, source: Path, anchor_maps: dict[Path, dict[str, str]]) -> str:
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

        output.append(convert_line(line, source, anchor_maps))

    if in_fence:
        raise ValueError("unterminated Markdown code fence")

    return "\n".join(output) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MediaWiki markup from Markdown")
    parser.add_argument("source", type=Path, help="Markdown source to convert")
    parser.add_argument("target", nargs="?", type=Path, help="MediaWiki target path")
    parser.add_argument("--check", action="store_true", help="fail if the target is not up to date")
    parser.add_argument("--target-for", action="store_true", help="print the generated target path for source")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source
    target = args.target or mediawiki_target(source)

    if args.target_for:
        print(target.relative_to(ROOT) if target.is_absolute() and target.is_relative_to(ROOT) else target)
        return 0

    try:
        generated = convert_markdown(source.read_text(encoding="utf-8"), source, all_anchor_maps())
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
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(generated, encoding="utf-8")
    except OSError as error:
        print(f"error writing {target}: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
