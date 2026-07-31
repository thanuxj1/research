"""
Review Analyzer — Mines Reviews.csv for tourist safety patterns.
IT22629180

Extracts:
  - Seasonal risk curves (monthly safety index per city)
  - Location-type risk profiles (beaches vs temples vs markets)
  - Nationality-based vulnerability (first-timer vs experienced traveller)
  - Negative-review sentiment hotspots
  - Combined risk features for the ML training pipeline
"""
import os
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
_CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "Reviews.csv"
)

# ── Keyword lists for negative-experience detection ────────────────────────────
SCAM_KEYWORDS = [
    "scam", "ripped off", "overcharged", "fake", "fraud", "cheat",
    "trick", "stolen", "harass", "unsafe", "dangerous", "beware",
    "avoid", "warning", "terrible", "awful", "horrible",
    "aggressive", "pushy", "commission", "gem", "tuk tuk", "tuk-tuk",
]

SAFETY_KEYWORDS = [
    "safe", "peaceful", "friendly", "welcoming", "clean", "secure",
    "recommend", "beautiful", "amazing", "wonderful", "perfect",
]

# ── Location type → base risk level mapping ───────────────────────────────────
LOCATION_TYPE_BASE_RISK: Dict[str, float] = {
    "Religious Sites":        0.45,   # Fake guides, dress-code exploitation
    "Beaches":                0.55,   # Beach boys, harassment, theft
    "Markets":                0.65,   # Overcharging, pickpockets
    "Shopping":               0.60,   # Gem scams, overcharging
    "Historic Sites":         0.50,   # Fake guides, overcharging
    "Farms":                  0.20,   # Generally safe
    "Nature & Wildlife Areas": 0.25,  # Generally safe, some transport risk
    "Museums":                0.20,   # Generally safe
    "Gardens":                0.20,   # Generally safe
    "National Parks":         0.30,   # Transport scams
    "Waterfalls":             0.35,   # Transport to remote areas
    "Bodies of Water":        0.35,   # Safety/accident risk
    "Spas & Wellness":        0.30,   # Overcharging
    "Points of Interest":     0.40,   # Mixed
    "Monuments":              0.45,   # Fake guides
    "Neighborhood":           0.50,   # Variable
    "Other":                  0.40,
}

# ── Month → monsoon risk boost ────────────────────────────────────────────────
# SW Monsoon: May–Sep (west/south coast)
# NE Monsoon: Oct–Jan (east/north coast)
MONTH_RISK_BOOST: Dict[int, float] = {
    1: 0.05, 2: 0.00, 3: 0.00, 4: 0.05,
    5: 0.15, 6: 0.20, 7: 0.18, 8: 0.15,
    9: 0.10, 10: 0.12, 11: 0.10, 12: 0.05,
}

# ── Cities that map to known coordinates ─────────────────────────────────────
CITY_COORDS: Dict[str, Tuple[float, float]] = {
    "Colombo": (6.9271, 79.8612),
    "Kandy": (7.2906, 80.6337),
    "Galle": (6.0535, 80.2210),
    "Sigiriya": (7.9570, 80.7603),
    "Ella": (6.8667, 81.0500),
    "Nuwara Eliya": (6.9497, 80.7891),
    "Anuradhapura": (8.3114, 80.4037),
    "Mirissa": (5.9483, 80.4716),
    "Hikkaduwa": (6.1395, 80.1067),
    "Jaffna": (9.6615, 80.0255),
    "Polonnaruwa": (7.9403, 81.0188),
    "Habarana": (8.0500, 80.7500),
    "Trincomalee": (8.5874, 81.2152),
    "Arugam Bay": (6.8401, 81.8303),
    "Bentota": (6.4219, 80.0001),
    "Negombo": (7.2081, 79.8358),
    "Unawatuna": (6.0108, 80.2491),
    "Dambulla": (7.8742, 80.6511),
    "Matara": (5.9549, 80.5550),
    "Weligama": (5.9747, 80.4297),
}


class ReviewAnalyzer:
    """
    Parses Reviews.csv and extracts ML-ready features and insights.
    """

    def __init__(self, csv_path: str = _CSV_PATH):
        self._csv_path = csv_path
        self._df = None
        self._loaded = False

        # Computed features
        self.seasonal_risk: Dict[str, Dict[int, float]] = {}   # city → {month → risk}
        self.location_type_risk: Dict[str, float] = {}         # location_type → risk
        self.city_scam_profile: Dict[str, Dict] = {}           # city → {scam stats}
        self.nationality_risk: Dict[str, float] = {}           # country → risk multiplier
        self.pattern_insights: List[Dict] = []                 # top ML-discovered patterns

    # ── Public API ─────────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Load and preprocess Reviews.csv. Returns True if successful."""
        try:
            import pandas as pd
            if not os.path.exists(self._csv_path):
                print(f"[ReviewAnalyzer] CSV not found at {self._csv_path}")
                return False

            self._df = pd.read_csv(self._csv_path, encoding="latin-1")
            self._preprocess()
            self._loaded = True
            print(f"[ReviewAnalyzer] Loaded {len(self._df)} reviews.")
            return True
        except Exception as e:
            print(f"[ReviewAnalyzer] Failed to load CSV: {e}")
            return False

    def analyze(self) -> Dict:
        """
        Run all analyses. Returns a summary dict with all computed features.
        Call load() first.
        """
        if not self._loaded:
            return {}

        self._compute_location_type_risk()
        self._compute_seasonal_risk()
        self._compute_city_scam_profiles()
        self._compute_nationality_risk()
        self._extract_pattern_insights()

        return {
            "total_reviews":      len(self._df),
            "cities_analyzed":    len(self.city_scam_profile),
            "location_types":     len(self.location_type_risk),
            "pattern_count":      len(self.pattern_insights),
        }

    def get_location_risk_boost(self, location_type: str, month: int) -> float:
        """Returns total risk boost for a location type + travel month."""
        base = self.location_type_risk.get(
            location_type,
            LOCATION_TYPE_BASE_RISK.get(location_type, 0.40)
        )
        seasonal = MONTH_RISK_BOOST.get(month, 0.0)
        return round(min(base + seasonal, 1.0), 4)

    def get_city_profile(self, city: str) -> Optional[Dict]:
        """Returns scam/safety profile for a city."""
        # Exact match first
        if city in self.city_scam_profile:
            return self.city_scam_profile[city]
        # Partial match
        city_lower = city.lower()
        for k, v in self.city_scam_profile.items():
            if city_lower in k.lower() or k.lower() in city_lower:
                return v
        return None

    def get_seasonal_risk(self, city: str, month: int) -> float:
        """Returns the seasonal risk index for a city in a given month (0–1)."""
        if city in self.seasonal_risk:
            return self.seasonal_risk[city].get(month, 0.35)
        return MONTH_RISK_BOOST.get(month, 0.05) + 0.30

    def get_top_patterns(self, limit: int = 20) -> List[Dict]:
        """Returns top ML-extracted patterns sorted by incident density."""
        return self.pattern_insights[:limit]

    def build_training_rows(self) -> List[Dict]:
        """
        Build augmented training rows from Reviews CSV.
        Each row is a dict with features that can be merged with DB records.
        """
        if not self._loaded or self._df is None:
            return []

        rows = []
        df = self._df

        for _, row in df.iterrows():
            try:
                city = str(row.get("Located_City", "") or "")
                loc_type = str(row.get("Location_Type", "") or "")
                rating = float(row.get("Rating", 3) or 3)
                text = str(row.get("Text", "") or "")
                title = str(row.get("Title", "") or "")
                combined_text = (title + " " + text).lower()
                month = self._parse_month(str(row.get("Travel_Date", "") or ""))
                contributions = int(row.get("User_Contributions", 1) or 1)
                user_location = str(row.get("User_Location", "") or "")
                country = self._extract_country(user_location)

                # Compute derived features
                neg_score = self._neg_score(combined_text)
                is_negative = rating <= 2 or neg_score >= 2
                is_very_negative = rating == 1 or neg_score >= 3
                is_experienced = contributions >= 50
                loc_risk = LOCATION_TYPE_BASE_RISK.get(loc_type, 0.40)
                month_boost = MONTH_RISK_BOOST.get(month, 0.0)

                # Inferred risk level from review data
                if is_very_negative:
                    risk_level = 3
                elif is_negative:
                    risk_level = 2
                else:
                    risk_level = 1

                # Coords from city lookup
                coords = CITY_COORDS.get(city)
                lat = coords[0] if coords else None
                lon = coords[1] if coords else None

                rows.append({
                    "source":        "reviews_csv",
                    "city":          city,
                    "location_type": loc_type,
                    "lat":           lat,
                    "lon":           lon,
                    "rating":        rating,
                    "month":         month,
                    "neg_score":     neg_score,
                    "is_negative":   int(is_negative),
                    "is_experienced": int(is_experienced),
                    "loc_risk":      loc_risk,
                    "month_boost":   month_boost,
                    "country":       country,
                    "risk_level":    risk_level,
                    "is_scam":       int(is_negative and neg_score >= 2),
                })
            except Exception:
                continue

        return rows

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _preprocess(self):
        """Clean and add derived columns to the dataframe."""
        import pandas as pd

        df = self._df
        df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce").fillna(3)
        df["User_Contributions"] = pd.to_numeric(
            df["User_Contributions"], errors="coerce"
        ).fillna(1)
        df["month"] = df["Travel_Date"].apply(
            lambda x: self._parse_month(str(x) if x else "")
        )
        df["country"] = df["User_Location"].apply(
            lambda x: self._extract_country(str(x) if x else "")
        )
        combined = (
            df["Title"].fillna("") + " " + df["Text"].fillna("")
        ).str.lower()
        df["neg_score"] = combined.apply(self._neg_score)
        df["pos_score"] = combined.apply(self._pos_score)
        df["is_negative"] = (df["Rating"] <= 2) | (df["neg_score"] >= 2)
        df["is_very_negative"] = (df["Rating"] == 1) | (df["neg_score"] >= 3)
        self._df = df

    def _compute_location_type_risk(self):
        """Compute empirical risk by location type from review ratings."""
        df = self._df
        groups = df.groupby("Location_Type")
        for loc_type, grp in groups:
            avg_rating = grp["Rating"].mean()
            neg_rate = grp["is_negative"].mean()
            scam_rate = (grp["neg_score"] >= 2).mean()

            # Normalise: 1-star avg → risk 1.0, 5-star → risk 0.0
            rating_risk = (5 - avg_rating) / 4
            combined_risk = rating_risk * 0.5 + neg_rate * 0.3 + scam_rate * 0.2
            base = LOCATION_TYPE_BASE_RISK.get(str(loc_type), 0.40)
            # Blend empirical with prior
            self.location_type_risk[str(loc_type)] = round(
                combined_risk * 0.6 + base * 0.4, 4
            )

    def _compute_seasonal_risk(self):
        """Compute month-by-month risk index per city."""
        df = self._df
        groups = df.groupby(["Located_City", "month"])
        city_month_data = defaultdict(lambda: defaultdict(list))
        for (city, month), grp in groups:
            neg_rate = grp["is_negative"].mean()
            avg_rating = grp["Rating"].mean()
            risk = (5 - avg_rating) / 4 * 0.6 + neg_rate * 0.4
            city_month_data[str(city)][int(month)].append(risk)

        for city, months in city_month_data.items():
            self.seasonal_risk[city] = {
                m: round(float(np.mean(vals)), 4)
                for m, vals in months.items()
            }

    def _compute_city_scam_profiles(self):
        """Build per-city risk and scam profile from reviews."""
        df = self._df
        groups = df.groupby("Located_City")
        for city, grp in groups:
            total = len(grp)
            neg = int(grp["is_negative"].sum())
            very_neg = int(grp["is_very_negative"].sum())
            avg_rating = round(float(grp["Rating"].mean()), 2)
            scam_mentions = int((grp["neg_score"] >= 2).sum())
            avg_contributions = round(float(grp["User_Contributions"].mean()), 1)
            top_location_types = (
                grp["Location_Type"].value_counts().head(3).to_dict()
            )

            # Peak complaint months
            neg_df = grp[grp["is_negative"]]
            peak_months: List[int] = []
            if len(neg_df) > 0:
                peak_months = (
                    neg_df["month"].value_counts().head(3).index.tolist()
                )

            risk_score = round(
                (5 - avg_rating) / 4 * 0.5
                + (neg / total) * 0.3
                + (scam_mentions / total) * 0.2,
                4,
            )
            coords = CITY_COORDS.get(str(city))

            self.city_scam_profile[str(city)] = {
                "total_reviews":      total,
                "negative_reviews":   neg,
                "very_negative":      very_neg,
                "avg_rating":         avg_rating,
                "scam_mentions":      scam_mentions,
                "avg_contributions":  avg_contributions,
                "top_location_types": top_location_types,
                "peak_complaint_months": [int(m) for m in peak_months],
                "risk_score":         risk_score,
                "lat":                coords[0] if coords else None,
                "lon":                coords[1] if coords else None,
            }

    def _compute_nationality_risk(self):
        """Estimate vulnerability by country — less experienced travellers score higher."""
        df = self._df
        groups = df.groupby("country")
        for country, grp in groups:
            if not country or country == "Unknown":
                continue
            avg_contrib = grp["User_Contributions"].mean()
            neg_rate = grp["is_negative"].mean()
            # Lower contributions → less experienced → higher multiplier
            experience_factor = max(0.0, 1.0 - (avg_contrib / 200))
            multiplier = round(1.0 + experience_factor * 0.3 + neg_rate * 0.2, 3)
            self.nationality_risk[str(country)] = min(multiplier, 1.8)

    def _extract_pattern_insights(self):
        """Mine top recurring patterns: city × location_type × month combinations."""
        df = self._df
        # Only look at clearly negative reviews
        neg_df = df[df["is_negative"]]
        if neg_df.empty:
            return

        groups = neg_df.groupby(["Located_City", "Location_Type", "month"])
        patterns = []
        for (city, loc_type, month), grp in groups:
            if len(grp) < 3:
                continue
            avg_rating = float(grp["Rating"].mean())
            scam_mentions = int((grp["neg_score"] >= 2).sum())
            density = len(grp)
            coords = CITY_COORDS.get(str(city))
            patterns.append({
                "city":            str(city),
                "location_type":   str(loc_type),
                "month":           int(month),
                "month_name":      _MONTH_NAMES.get(int(month), "Unknown"),
                "incident_count":  density,
                "avg_rating":      round(avg_rating, 2),
                "scam_mentions":   scam_mentions,
                "risk_score":      round((5 - avg_rating) / 4 * 0.6 + scam_mentions / max(density, 1) * 0.4, 4),
                "lat":             coords[0] if coords else None,
                "lon":             coords[1] if coords else None,
                "insight":         self._build_insight_text(str(city), str(loc_type), int(month), density, scam_mentions),
            })

        self.pattern_insights = sorted(
            patterns, key=lambda x: x["incident_count"], reverse=True
        )

    # ── Utility ────────────────────────────────────────────────────────────────

    def _neg_score(self, text: str) -> int:
        return sum(1 for kw in SCAM_KEYWORDS if kw in text)

    def _pos_score(self, text: str) -> int:
        return sum(1 for kw in SAFETY_KEYWORDS if kw in text)

    def _parse_month(self, date_str: str) -> int:
        """Extract month integer from 'YYYY-MM' or 'YYYY-MM-DDTHH...' strings."""
        if not date_str or date_str == "nan":
            return 6  # Default mid-year
        parts = re.split(r"[-T]", date_str.strip())
        try:
            return int(parts[1]) if len(parts) >= 2 else 6
        except (ValueError, IndexError):
            return 6

    def _extract_country(self, user_location: str) -> str:
        """Extract country from 'City, Country' string."""
        if not user_location or user_location == "nan":
            return "Unknown"
        parts = user_location.rsplit(",", 1)
        return parts[-1].strip() if len(parts) > 1 else "Unknown"

    def _build_insight_text(
        self, city: str, loc_type: str, month: int, count: int, scam_mentions: int
    ) -> str:
        month_name = _MONTH_NAMES.get(month, "this time of year")
        scam_part = f" with {scam_mentions} scam-related mentions" if scam_mentions > 0 else ""
        return (
            f"{count} negative reviews at {loc_type.lower()} in {city}"
            f" during {month_name}{scam_part}."
        )


_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


# ── Singleton ─────────────────────────────────────────────────────────────────
_analyzer: Optional[ReviewAnalyzer] = None


def get_analyzer() -> ReviewAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = ReviewAnalyzer()
        _analyzer.load()
        _analyzer.analyze()
    return _analyzer
