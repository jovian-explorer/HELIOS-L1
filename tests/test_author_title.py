"""The author's name and role are shown exactly as the owner gave them."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "README.md", ROOT / "helios" / "gui" / "static" / "index.html",
         ROOT / "helios" / "core" / "spice_engine.py"]


def test_author_title_and_role():
    for p in FILES:
        text = p.read_text(encoding="utf-8")
        assert "Dr. Keshav" not in text and "DR. KESHAV" not in text, p.name
        assert "Research Associate" not in text, p.name
        assert "completed his" not in text, p.name
    for p in FILES[:2]:
        assert "Student Visitor" in p.read_text(encoding="utf-8"), p.name
