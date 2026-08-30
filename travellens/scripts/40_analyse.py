"""Analyse a single review. This is the portal's engine.

  python scripts/40_analyse.py "The road was terrible but the view is stunning."
  python scripts/40_analyse.py --fast "..."             (lexicon only; weaker)
  echo "..." | python scripts/40_analyse.py             (from stdin)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.analyse import analyse, format_report  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:]]
    use_transformer = "--fast" not in args
    args = [a for a in args if a != "--fast"]

    text = " ".join(args).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        print(__doc__)
        raise SystemExit(1)

    print("\nLostinSriLanka -- single review analysis")
    print("=" * 60)
    res = analyse(text, use_transformer=use_transformer)
    print(format_report(res))


if __name__ == "__main__":
    main()
