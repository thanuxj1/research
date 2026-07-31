"""
Pattern Predictor — Random Forest ML model for Tourist Safety
IT22629180

Trains on all geolocated DB records and predicts:
  - risk_level (1=Low, 2=Moderate, 3=High)
  - confidence score
  - expected scam types for a given lat/lon + traveller profile

Also exports:
  SL_LOCATIONS_FOR_SAFE_ZONES — full dict of known SL places with coordinates
"""
import os
import math
import joblib
import numpy as np
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple
from app.ml.source_weights import get_source_weight, get_weight_tier_label

# ─── Graceful sklearn import ─────────────────────────────────────────────────
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import LabelEncoder
    from sklearn.model_selection import cross_val_score
    from sklearn.metrics import accuracy_score, classification_report
    _SKLEARN_OK = True
except ImportError:
    _SKLEARN_OK = False
    print("[ML] scikit-learn not available — rule-based predictor will be used.")


# ─── Profile → High-Risk Scam Types mapping ──────────────────────────────────
PROFILE_RISK_MAP: Dict[str, List[str]] = {
    "Solo Female":    ["Harassment", "Physical Assault", "Unsafe Area", "Tuk Tuk Scam", "Accommodation Scam"],
    "Solo Male":      ["Gem Scam", "Tuk Tuk Scam", "Overcharging", "Transport Fraud", "Fake Guide"],
    "Couple":         ["Gem Scam", "Tuk Tuk Scam", "Overcharging", "Accommodation Scam", "Food/Menu Scam"],
    "Family":         ["Health / Hygiene", "Accommodation Scam", "Food/Menu Scam", "Transport Fraud", "Accident / Hazard"],
    "Group":          ["Overcharging", "Gem Scam", "Fake Guide", "Transport Fraud", "Tuk Tuk Scam"],
    "General":        ["Tuk Tuk Scam", "Gem Scam", "Overcharging", "Fake Guide", "Harassment"],
}

# Profile demographic multipliers for risk scoring
PROFILE_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "Solo Female": {
        "Harassment": 2.0, "Physical Assault": 1.8, "Unsafe Area": 1.7,
        "Accommodation Scam": 1.4, "Theft / Robbery": 1.3,
    },
    "Solo Male": {
        "Gem Scam": 1.6, "Tuk Tuk Scam": 1.4, "Overcharging": 1.3,
        "Transport Fraud": 1.3, "Fake Guide": 1.4,
    },
    "Couple": {
        "Gem Scam": 1.5, "Accommodation Scam": 1.4, "Food/Menu Scam": 1.3,
        "Overcharging": 1.2,
    },
    "Family": {
        "Health / Hygiene": 1.8, "Accident / Hazard": 1.7,
        "Food/Menu Scam": 1.6, "Accommodation Scam": 1.5,
    },
    "Group": {
        "Overcharging": 1.5, "Transport Fraud": 1.4, "Fake Guide": 1.4,
    },
    "General": {},
}

# Personalized safety tips per profile + scam type
SAFETY_TIPS: Dict[str, List[Dict]] = {
    "Solo Female": [
        {"icon": "🚫", "title": "Avoid Isolated Areas at Night",
         "body": "Stick to well-lit, populated areas. Beaches like Mirissa and Hikkaduwa can attract 'beach boys' after dark."},
        {"icon": "🛺", "title": "Pre-Negotiate Tuk-Tuk Fares",
         "body": "Always agree on a price before you get in. Use apps like PickMe or Uber where available in Colombo."},
        {"icon": "🏨", "title": "Book Accommodation in Advance",
         "body": "Don't let strangers take you to 'better' guesthouses — they earn commissions and you often pay more."},
        {"icon": "📍", "title": "Share Your Location",
         "body": "Always share your live GPS location with a friend or family member when moving between cities."},
        {"icon": "👗", "title": "Dress Modestly at Religious Sites",
         "body": "Cover shoulders and knees at temples to avoid unsolicited 'guides' who exploit dress-code confusion."},
        {"icon": "🆘", "title": "Sri Lanka Tourist Police",
         "body": "Tourist Police Hotline: 1912. Save this number. They have English-speaking officers."},
    ],
    "Solo Male": [
        {"icon": "💎", "title": "Gem Shop Commission Scam",
         "body": "If a tuk-tuk driver offers to take you somewhere 'special', they earn commissions. Politely decline gem shops."},
        {"icon": "🧑‍🦯", "title": "Fake Temple Guides",
         "body": "At Sigiriya and Kandy, unofficial guides approach with 'free' tours that end in demands for large tips."},
        {"icon": "💰", "title": "Double-Check Restaurant Bills",
         "body": "Tourist menus with inflated prices are common. Always check the bill carefully before paying."},
        {"icon": "🚕", "title": "Use Metered Taxis",
         "body": "At the Colombo airport, use the official pre-paid taxi counter. Unofficial drivers charge 3–5x the real rate."},
        {"icon": "🍺", "title": "Beware of 'Friendly' Strangers",
         "body": "People who befriend you near tourist spots and offer to share meals or drinks may run overcharging scams."},
        {"icon": "🆘", "title": "Emergency Contact",
         "body": "Police: 119 | Tourist Helpline: 1912 | Ambulance: 110"},
    ],
    "Couple": [
        {"icon": "💎", "title": "Gem Investment Scams",
         "body": "Couples are prime targets for gem dealers claiming to offer 'once in a lifetime' investment deals. Always refuse."},
        {"icon": "🏨", "title": "Verify Hotel Bookings",
         "body": "Confirm your hotel directly. Some touts show fake booking confirmations and take you to substandard properties."},
        {"icon": "🍽️", "title": "Menu Price Traps",
         "body": "Romantic beachside restaurants sometimes present tourist menus. Ask to see the price menu before ordering."},
        {"icon": "📷", "title": "Unsolicited Photographers",
         "body": "Strangers offering to take your photo near monuments may demand money afterwards."},
        {"icon": "🛺", "title": "Tuk-Tuk Day Tours",
         "body": "Agree on a full-day price upfront. Include fuel costs in the negotiation — some drivers ask for extra mid-trip."},
        {"icon": "🆘", "title": "Emergency Contact",
         "body": "Tourist Police: 1912 | Hospital (Colombo): +94 11 269 1111"},
    ],
    "Family": [
        {"icon": "🍼", "title": "Food & Water Safety",
         "body": "Stick to bottled water. Avoid raw salads and ice in non-tourist-grade restaurants to prevent food poisoning."},
        {"icon": "🚌", "title": "Safe Transport",
         "body": "Use reputable hired vehicles with air-conditioning for long trips. Avoid cramped local buses with young children."},
        {"icon": "🏥", "title": "Medical Preparedness",
         "body": "Carry basic medication: oral rehydration salts, antihistamines, and sunscreen. Pharmacies are widely available."},
        {"icon": "🌊", "title": "Ocean & Pool Safety",
         "body": "Many Sri Lanka beaches have strong rip currents. Swim only at beaches with lifeguards and check flags daily."},
        {"icon": "🦟", "title": "Mosquito Protection",
         "body": "Dengue fever is present. Use DEET repellent, especially in the evening. Keep children covered."},
        {"icon": "🆘", "title": "Child Safety Tip",
         "body": "Always keep children close in busy markets like Pettah (Colombo). Use a wristband with your phone number."},
    ],
    "Group": [
        {"icon": "💰", "title": "Group Overcharging",
         "body": "Larger groups are often quoted inflated prices. Always negotiate as if you have fewer people, then confirm total."},
        {"icon": "🚌", "title": "Private Vehicle Scams",
         "body": "For group transport, book through your hotel. Drivers who approach groups at stations often overcharge by 3–4x."},
        {"icon": "🧑‍🦯", "title": "Fake Tour Guides",
         "body": "Groups attract unofficial guides at every major attraction. Only hire guides with official badges."},
        {"icon": "🍽️", "title": "Restaurant Bills for Groups",
         "body": "Always designate one person to check the itemised bill. Service charges and extras get added for large tables."},
        {"icon": "📦", "title": "Luggage Theft",
         "body": "In busy train stations (Colombo Fort, Kandy), keep an eye on shared luggage. Thieves work in groups too."},
        {"icon": "🆘", "title": "Emergency",
         "body": "Tourist Police: 1912 | Keep the group's leader phone numbers exchanged at the start of every day."},
    ],
    "General": [
        {"icon": "🛺", "title": "Tuk-Tuk Scams Are #1",
         "body": "Always negotiate the fare BEFORE getting in. The biggest scam in Sri Lanka — especially around Colombo Fort and Kandy."},
        {"icon": "💎", "title": "Gem Shop Redirect",
         "body": "Drivers redirecting you to gem or spice shops earn high commissions. You are under no obligation to enter."},
        {"icon": "💰", "title": "Overcharging at Attractions",
         "body": "There are official government ticket prices for all major sites. Verify at the official counter — never from touts."},
        {"icon": "🧑‍🦯", "title": "Unofficial Guides",
         "body": "Sigiriya, Galle Fort, and Temple of the Tooth: only use guides with government-issued ID badges."},
        {"icon": "📱", "title": "Use PickMe App",
         "body": "PickMe is Sri Lanka's Uber equivalent. Use it in Colombo and major cities to avoid taxi price negotiation."},
        {"icon": "🆘", "title": "Tourist Police Hotline",
         "body": "Call 1912 for the Sri Lanka Tourist Police — English speaking, 24/7."},
    ],
}


class PatternPredictor:
    """
    Random Forest pattern predictor trained on existing DB safety reports.
    Falls back to rule-based scoring if sklearn is unavailable.
    """

    MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "pattern_rf.joblib")
    META_PATH  = os.path.join(os.path.dirname(__file__), "models", "pattern_meta.joblib")

    def __init__(self):
        self._model: Optional[RandomForestClassifier] = None
        self._scam_encoder   = LabelEncoder() if _SKLEARN_OK else None
        self._source_encoder = LabelEncoder() if _SKLEARN_OK else None
        self._trained        = False
        self._accuracy       = 0.0
        self._feature_importance: Dict[str, float] = {}
        self._training_size  = 0
        self._location_risk_cache: Dict[Tuple, Dict] = {}   # (lat_bin, lon_bin) → stats
        self._class_labels   = [1, 2, 3]

    # ── Public API ────────────────────────────────────────────────────────────

    def train(self, reports: list) -> Dict:
        """
        Train the Random Forest on a list of Report ORM objects.
        Returns training metrics dict.
        """
        if not reports:
            print("[ML] No records to train on.")
            return {"status": "no_data"}

        # Build location risk cache (always — even if sklearn unavailable)
        self._build_location_cache(reports)

        if not _SKLEARN_OK:
            self._trained = True
            self._training_size = len(reports)
            return {"status": "rule_based", "training_size": len(reports)}

        X, y = self._build_features(reports)
        if len(X) < 10:
            print("[ML] Too few samples to train.")
            return {"status": "insufficient_data"}

        # Fit model
        self._model = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_split=3,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X, y)

        # Cross-val accuracy
        try:
            cv_scores = cross_val_score(self._model, X, y, cv=min(5, len(set(y))), scoring="accuracy")
            self._accuracy = float(np.mean(cv_scores))
        except Exception:
            preds = self._model.predict(X)
            self._accuracy = float(accuracy_score(y, preds))

        # Feature importance
        feat_names = ["lat_bin", "lon_bin", "scam_encoded", "source_encoded", "is_scam"]
        self._feature_importance = {
            name: round(float(imp), 4)
            for name, imp in zip(feat_names, self._model.feature_importances_)
        }

        self._trained = True
        self._training_size = len(X)

        # Persist model
        os.makedirs(os.path.dirname(self.MODEL_PATH), exist_ok=True)
        joblib.dump(self._model, self.MODEL_PATH)
        joblib.dump({
            "scam_encoder": self._scam_encoder,
            "source_encoder": self._source_encoder,
            "accuracy": self._accuracy,
            "feature_importance": self._feature_importance,
            "training_size": self._training_size,
        }, self.META_PATH)

        print(f"[ML] Random Forest trained — {len(X)} samples, accuracy={self._accuracy:.2%}")
        return {
            "status": "trained",
            "training_size": len(X),
            "accuracy": self._accuracy,
            "feature_importance": self._feature_importance,
        }

    def predict(self, lat: float, lon: float, profile: str = "General") -> Dict:
        """
        Predict risk for a location + traveller profile.
        Returns: risk_level, confidence, expected_scams, safety_score, tips
        """
        lat_bin = round(lat, 2)
        lon_bin = round(lon, 2)

        # Get location stats from cache
        loc_stats = self._location_risk_cache.get((lat_bin, lon_bin)) or \
                    self._nearest_zone_stats(lat_bin, lon_bin)

        # ML prediction
        rf_risk = self._rf_predict(lat_bin, lon_bin)

        # Merge RF + location cache
        base_risk = rf_risk if rf_risk else (loc_stats.get("avg_risk", 1.5) if loc_stats else 1.5)

        # Apply profile demographic multiplier
        adjusted_risk = self._apply_profile_adjustment(base_risk, profile, loc_stats)

        # Clamp to 1–3
        predicted_risk = max(1, min(3, round(adjusted_risk)))
        safety_score   = round(100 - ((adjusted_risk - 1) / 2) * 100)

        # Expected scam types
        loc_scams    = loc_stats.get("scam_types", {}) if loc_stats else {}
        profile_risk = PROFILE_RISK_MAP.get(profile, PROFILE_RISK_MAP["General"])
        expected_scams = self._build_expected_scams(loc_scams, profile_risk, profile)

        # Confidence
        if self._trained and self._model and _SKLEARN_OK:
            confidence = min(0.95, self._accuracy + 0.05)
        elif loc_stats and loc_stats.get("report_count", 0) > 5:
            confidence = 0.78
        elif loc_stats and loc_stats.get("report_count", 0) > 0:
            confidence = 0.60
        else:
            confidence = 0.42   # Low confidence for unknown area

        return {
            "lat":             lat,
            "lon":             lon,
            "profile":         profile,
            "predicted_risk":  predicted_risk,
            "risk_label":      ["", "Low", "Moderate", "High"][predicted_risk],
            "safety_score":    safety_score,
            "confidence":      round(confidence, 3),
            "expected_scams":  expected_scams,
            "report_count":    loc_stats.get("report_count", 0) if loc_stats else 0,
            "nearest_location": loc_stats.get("location_name") if loc_stats else None,
            "model_used":      "RandomForest" if (self._trained and self._model) else "RuleBased",
        }

    def get_model_stats(self) -> Dict:
        """Returns model metadata and performance metrics."""
        return {
            "trained":            self._trained,
            "model_type":         "RandomForestClassifier" if _SKLEARN_OK else "RuleBased",
            "training_size":      self._training_size,
            "accuracy":           round(self._accuracy, 4),
            "feature_importance": self._feature_importance,
            "sklearn_available":  _SKLEARN_OK,
            "cached_zones":       len(self._location_risk_cache),
        }

    def get_safe_zones(self, all_sl_locations: Dict[str, Tuple]) -> List[Dict]:
        """
        Returns safe zones (risk_score < 0.2) from the known SL locations list.
        Locations with no reports at all are also considered safe.
        """
        safe = []
        for name, (lat, lon) in all_sl_locations.items():
            lat_bin = round(lat, 2)
            lon_bin = round(lon, 2)
            stats = self._location_risk_cache.get((lat_bin, lon_bin))

            if stats is None:
                # No incidents recorded → safe
                safe.append({
                    "name":         name.title(),
                    "lat":          lat,
                    "lon":          lon,
                    "risk_score":   0.0,
                    "report_count": 0,
                    "safety_score": 100,
                    "status":       "No incidents recorded",
                })
            elif stats.get("risk_score", 1.0) < 0.20:
                safe.append({
                    "name":         name.title(),
                    "lat":          lat,
                    "lon":          lon,
                    "risk_score":   stats["risk_score"],
                    "report_count": stats.get("report_count", 0),
                    "safety_score": round(100 - stats["risk_score"] * 100),
                    "status":       "Very low incident rate",
                })

        return sorted(safe, key=lambda x: x["risk_score"])

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_location_cache(self, reports: list):
        """Build a lat/lon → stats dict using source-weighted risk scores."""
        groups: Dict[Tuple, list] = defaultdict(list)
        for r in reports:
            lat = getattr(r, "latitude", None)
            lon = getattr(r, "longitude", None)
            if lat is None or lon is None:
                continue
            key = (round(lat, 2), round(lon, 2))
            groups[key].append(r)

        for key, grp in groups.items():
            scam_types: Dict[str, int] = {}
            weighted_risk_sum = 0.0
            weight_total = 0.0
            scam_count = 0
            loc_name = None

            for r in grp:
                # Use stored source_weight; fall back to get_source_weight by source name
                sw = getattr(r, "source_weight", None)
                if sw is None or sw <= 0:
                    sw = get_source_weight(getattr(r, "source", "unknown"))

                rl = getattr(r, "risk_level", 1) or 1
                weighted_risk_sum += rl * sw
                weight_total += sw

                st = getattr(r, "scam_type", None)
                if st:
                    scam_types[st] = scam_types.get(st, 0) + 1
                if getattr(r, "is_scam", False):
                    scam_count += 1
                if not loc_name:
                    loc_name = getattr(r, "location_name", None)

            n = len(grp)
            # Weighted average risk (higher-trust sources count more)
            avg_risk = (weighted_risk_sum / weight_total) if weight_total > 0 else 1.0
            scam_ratio = scam_count / n
            risk_score = min(avg_risk / 3 * 0.75 + scam_ratio * 0.25, 1.0)
            avg_weight = weight_total / n   # Average credibility of reports at this location

            self._location_risk_cache[key] = {
                "report_count": n,
                "avg_risk":     round(avg_risk, 3),
                "scam_ratio":   round(scam_ratio, 3),
                "risk_score":   round(risk_score, 4),
                "scam_types":   scam_types,
                "location_name": loc_name,
                "avg_source_weight": round(avg_weight, 3),  # credibility of the evidence base
            }

    def _build_features(self, reports: list):
        """Build feature matrix X and label vector y for sklearn."""
        scam_types = [getattr(r, "scam_type", None) or "none" for r in reports]
        sources    = [getattr(r, "source", None) or "unknown" for r in reports]

        self._scam_encoder.fit(list(set(scam_types)))
        self._source_encoder.fit(list(set(sources)))

        X, y = [], []
        for r, st, src in zip(reports, scam_types, sources):
            lat = getattr(r, "latitude", None)
            lon = getattr(r, "longitude", None)
            rl  = getattr(r, "risk_level", 1) or 1
            if lat is None or lon is None:
                continue
            X.append([
                round(lat, 2),
                round(lon, 2),
                self._scam_encoder.transform([st])[0],
                self._source_encoder.transform([src])[0],
                int(getattr(r, "is_scam", False)),
            ])
            y.append(rl)

        return np.array(X), np.array(y)

    def _rf_predict(self, lat_bin: float, lon_bin: float) -> Optional[float]:
        """Run RF model prediction if trained."""
        if not (self._model and self._trained):
            return None
        try:
            # Use "none" scam type and "unknown" source for generic location query
            scam_enc = self._scam_encoder.transform(["none"])[0] \
                if "none" in self._scam_encoder.classes_ else 0
            src_enc  = self._source_encoder.transform(["unknown"])[0] \
                if "unknown" in self._source_encoder.classes_ else 0
            proba = self._model.predict_proba([[lat_bin, lon_bin, scam_enc, src_enc, 0]])[0]
            classes = self._model.classes_
            expected = sum(c * p for c, p in zip(classes, proba))
            return float(expected)
        except Exception as e:
            print(f"[ML] RF predict error: {e}")
            return None

    def _nearest_zone_stats(self, lat_bin: float, lon_bin: float) -> Optional[Dict]:
        """Find closest cached zone within 0.5 degrees."""
        best_dist = float("inf")
        best_stats = None
        for (lt, ln), stats in self._location_risk_cache.items():
            dist = math.sqrt((lat_bin - lt) ** 2 + (lon_bin - ln) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_stats = stats
        return best_stats if best_dist < 0.5 else None

    def _apply_profile_adjustment(self, base_risk: float, profile: str, loc_stats: Optional[Dict]) -> float:
        """Adjust risk score based on traveller profile."""
        multipliers = PROFILE_MULTIPLIERS.get(profile, {})
        if not loc_stats or not multipliers:
            return base_risk

        scam_types = loc_stats.get("scam_types", {})
        if not scam_types:
            return base_risk

        # Boost risk if profile-sensitive scams are present in this location
        boost = 0.0
        total_reports = loc_stats.get("report_count", 1)
        for scam, count in scam_types.items():
            mult = multipliers.get(scam, 1.0)
            if mult > 1.0:
                weight = count / total_reports
                boost += (mult - 1.0) * weight * base_risk

        return min(base_risk + boost, 3.0)

    def _build_expected_scams(
        self,
        loc_scams: Dict[str, int],
        profile_risks: List[str],
        profile: str,
    ) -> List[Dict]:
        """Build a ranked list of expected threats for this location + profile."""
        multipliers = PROFILE_MULTIPLIERS.get(profile, {})
        scored = {}

        # From location data
        total = sum(loc_scams.values()) or 1
        for scam, count in loc_scams.items():
            base = count / total
            mult = multipliers.get(scam, 1.0)
            scored[scam] = base * mult

        # Add profile-specific risks even if not in loc_scams
        for scam in profile_risks:
            if scam not in scored:
                scored[scam] = 0.1 * multipliers.get(scam, 1.0)

        # Sort and return top 5
        top = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:5]
        return [{"scam_type": s, "likelihood": round(min(v, 1.0), 3)} for s, v in top]


# ── Singleton ─────────────────────────────────────────────────────────────────
_predictor: Optional[PatternPredictor] = None


def get_predictor() -> PatternPredictor:
    global _predictor
    if _predictor is None:
        _predictor = PatternPredictor()
    return _predictor


# ── Re-export the SL locations dict so endpoints can import it ──────────────
from app.ml.nlp_pipeline import SL_LOCATIONS as SL_LOCATIONS_FOR_SAFE_ZONES  # noqa: E402
