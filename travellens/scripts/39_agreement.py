"""Entry point. Run: python scripts/39_agreement.py

Computes Cohen's kappa between the two human passes over the focused gold set
and writes reports/agreement.json. Refuses to run unless both label files
declare human provenance -- see src/travellens/agreement.py for why that
refusal is the point rather than an inconvenience.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from travellens.agreement import main

if __name__ == "__main__":
    main()
