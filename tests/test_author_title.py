"""The author's name and role are shown exactly as the owner gave them."""
from conftest import source_root


def test_author_title_and_role():
    root = source_root()   # README.md is not in the installed package
    files = [root / "README.md", root / "helios" / "gui" / "static" / "index.html",
             root / "helios" / "core" / "spice_engine.py"]
    for p in files:
        text = p.read_text(encoding="utf-8")
        assert "Dr. Keshav" not in text and "DR. KESHAV" not in text, p.name
        assert "Mr. Keshav" not in text, p.name
        assert "Research Associate" not in text, p.name
        assert "completed his" not in text, p.name
    for p in files[:2]:
        assert "Student Visitor" in p.read_text(encoding="utf-8"), p.name
