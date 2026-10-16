"""SVG output location: explicit output_svg works, conversion leaves no artifacts."""
import shutil

from typ2pptx.core.converter import compile_typst_to_svg, convert_typst_to_pptx
from typ2pptx.core.typst_svg_parser import parse_typst_svg


def _copy_source(typ_sources_dir, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    typ = src / "basic_text.typ"
    shutil.copy(typ_sources_dir / "basic_text.typ", typ)
    return typ


def test_compile_to_explicit_svg_path(typ_sources_dir, typst_ts_cli, tmp_path):
    typ = _copy_source(typ_sources_dir, tmp_path)
    out = tmp_path / "out" / "deck.svg"
    result = compile_typst_to_svg(str(typ), output_svg=str(out), typst_ts_cli=typst_ts_cli)
    assert result == str(out)
    assert parse_typst_svg(result).pages
    assert sorted(p.name for p in out.parent.iterdir()) == ["deck.svg"]  # scratch dir removed
    assert sorted(p.name for p in typ.parent.iterdir()) == ["basic_text.typ"]


def test_convert_leaves_no_artifact_next_to_source(typ_sources_dir, typst_ts_cli, tmp_path):
    typ = _copy_source(typ_sources_dir, tmp_path)
    out = tmp_path / "out.pptx"
    convert_typst_to_pptx(str(typ), str(out), typst_ts_cli=typst_ts_cli)
    assert out.is_file()
    assert sorted(p.name for p in typ.parent.iterdir()) == ["basic_text.typ"]
