"""Recover the font of each text segment from a PDF of the same document.

typst.ts SVG draws text as glyph outlines, and the only trace of the font is a
hashed glyph-ID prefix per font face. The PDF that typst-py exports for the
same source names the font of every glyph (``/BaseFont``), and since typst-py
is pinned to the Typst version of typst-ts-cli, both lay out the document
identically. Each glyph prefix is therefore matched to a PDF font by the
position of the text drawn with it.
"""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .typst_svg_parser import TypstSVGData

# How far apart (pt) a segment and a PDF glyph may be to count as the same text
_POSITION_TOLERANCE = 0.75

_BOLD_RE = re.compile(r'(?:semi|demi|extra|ultra)?bold|black|heavy', re.IGNORECASE)
_ITALIC_RE = re.compile(r'[Ii]talic|[Oo]blique|(?<![a-z])It$')
_MONO_RE = re.compile(
    r'mono|code|consol|courier|menlo|monaco|typewriter|inconsolata|iosevka|hack\b',
    re.IGNORECASE,
)


@dataclass
class PdfGlyph:
    """A character drawn in the PDF, with its origin in page coordinates."""
    char: str
    x: float
    baseline: float  # distance from the top of the page
    font_name: str  # PostScript name, without the subset tag


@dataclass
class ResolvedFont:
    """A font identified from its PostScript name."""
    postscript_name: str
    family: Optional[str]  # None when the font is not installed
    bold: bool
    italic: bool
    kind: str  # "text", "mono" or "math"

    @property
    def style(self) -> str:
        """The converter's font_variant name for this font."""
        if self.kind in ('mono', 'math'):
            return self.kind
        if self.bold and self.italic:
            return 'bolditalic'
        if self.bold:
            return 'bold'
        if self.italic:
            return 'italic'
        return 'regular'


def compile_pdf(typ_path: str, root: Optional[str] = None) -> bytes:
    """Compile a .typ file to PDF with the typst Python package."""
    import typst as typst_py

    kwargs = {"format": "pdf"}
    if root is not None:
        kwargs["root"] = root
    return typst_py.compile(str(Path(typ_path).resolve()), **kwargs)


def extract_pdf_glyphs(pdf: bytes) -> List[List[PdfGlyph]]:
    """List the glyphs of every page of a PDF, page by page."""
    import io

    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar

    def chars(item):
        if isinstance(item, LTChar):
            yield item
        elif hasattr(item, '__iter__'):
            for child in item:
                yield from chars(child)

    pages = []
    for page in extract_pages(io.BytesIO(pdf), laparams=LAParams()):
        glyphs = []
        for ch in chars(page):
            text = ch.get_text()
            if not text.strip():
                continue
            glyphs.append(PdfGlyph(
                char=text,
                x=ch.matrix[4],
                baseline=page.height - ch.matrix[5],
                font_name=ch.fontname.split('+', 1)[-1],
            ))
        pages.append(glyphs)
    return pages


def _normalize(name: str) -> str:
    return re.sub(r'[\s_-]', '', name).lower()


def resolve_font(postscript_name: str, families: Iterable[str]) -> ResolvedFont:
    """Find the family of a PostScript font name among the installed families.

    PostScript names drop the spaces of the family ("SourceHanSansJP-Bold" for
    "Source Han Sans JP"), so families are compared without spaces. The
    longest family that prefixes the name wins ("ArialMT" -> "Arial").
    A font that is not installed gets no family: naming it in the PPTX would
    only make PowerPoint substitute an arbitrary font.
    """
    family_part, _, style_part = postscript_name.partition('-')
    if not style_part:
        style_part = family_part

    target = _normalize(family_part)
    family = None
    best = 0
    for candidate in families:
        norm = _normalize(candidate)
        if norm and target.startswith(norm) and len(norm) > best:
            family, best = candidate, len(norm)

    lowered = postscript_name.lower()
    if 'math' in lowered:
        kind = 'math'
    elif _MONO_RE.search(family or family_part):
        kind = 'mono'
    else:
        kind = 'text'

    return ResolvedFont(
        postscript_name=postscript_name,
        family=family,
        bold=bool(_BOLD_RE.search(style_part)),
        italic=bool(_ITALIC_RE.search(style_part)),
        kind=kind,
    )


def installed_families() -> List[str]:
    """Font families installed on this system.

    Typst's bundled fonts (Libertinus Serif, New Computer Modern, DejaVu Sans
    Mono) are left out: PowerPoint on another machine will not have them.
    """
    import typst as typst_py

    return typst_py.Fonts(include_embedded_fonts=False).families()


def apply_pdf_fonts(
    svg_data: TypstSVGData,
    pdf_pages: Sequence[Sequence[PdfGlyph]],
    families: Iterable[str],
) -> Dict[str, ResolvedFont]:
    """Name the font of every glyph prefix and update the text segments.

    Each segment is matched to the PDF glyph at its origin (same page, same
    first character, same position), every match votes for its prefix's
    font, and the winning font sets the segment's font_variant and, when
    the font is installed, its font_family. Prefixes without a match keep
    the parser's heuristic style.

    Returns the resolved font of each prefix.
    """
    families = list(families)
    votes: Dict[str, Counter] = {}

    for page, glyphs in zip(svg_data.pages, pdf_pages):
        by_char: Dict[str, List[PdfGlyph]] = {}
        for g in glyphs:
            by_char.setdefault(g.char, []).append(g)

        for seg in page.text_segments:
            prefix = _segment_prefix(seg)
            text = seg.text.lstrip()
            if prefix is None or not text:
                continue
            baseline = seg.y + seg.font_size * 0.8
            # Leading spaces shift the first visible glyph right, so it only
            # has to start within one em of the segment.
            x_min = seg.x - _POSITION_TOLERANCE
            x_max = seg.x + seg.font_size + _POSITION_TOLERANCE
            for g in by_char.get(text[0], ()):
                if x_min <= g.x <= x_max and abs(g.baseline - baseline) <= _POSITION_TOLERANCE:
                    votes.setdefault(prefix, Counter())[g.font_name] += 1
                    break

    resolved = {
        prefix: resolve_font(counter.most_common(1)[0][0], families)
        for prefix, counter in votes.items()
    }

    for prefix, font in resolved.items():
        if prefix in svg_data.font_variants:
            svg_data.font_variants[prefix].style = font.style
            svg_data.font_variants[prefix].font_family = font.family

    for page in svg_data.pages:
        for seg in page.text_segments:
            font = resolved.get(_segment_prefix(seg))
            if font is not None:
                seg.font_variant = font.style
                seg.font_family = font.family

    return resolved


def _segment_prefix(seg) -> Optional[str]:
    """The glyph prefix (font face) a segment is drawn with."""
    prefixes = Counter(use.glyph_id[:5] for use in seg.glyph_uses)
    if not prefixes:
        return None
    return prefixes.most_common(1)[0][0]
