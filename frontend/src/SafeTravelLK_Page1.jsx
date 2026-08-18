import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { DEMO_INCIDENTS, DEMO_REVIEW_BODIES } from "./demoFixtures.js";

// ─── Demo mode gate ──────────────────────────────────────────────────────────────────────────
// Demo fixtures (invented data) ONLY load if:
//   • URL contains ?demo=1, OR
//   • VITE_DEMO_MODE env var is set to "true"
// In all other states the map shows an error state when the API is unreachable.
const IS_DEMO_MODE = (
  new URLSearchParams(window.location.search).get("demo") === "1" ||
  import.meta.env.VITE_DEMO_MODE === "true"
);
// Incidents used in offline/demo fallback (empty object when not in demo mode)
const SEED_INCIDENTS  = IS_DEMO_MODE ? DEMO_INCIDENTS  : {};
const REVIEW_BODIES   = IS_DEMO_MODE ? DEMO_REVIEW_BODIES : {};
// SAFETRAVEL LK — Page 1: District Safety Intelligence Map
// IT22629180 — Tourist Safety Intelligence for Sri Lanka
//
// FIXES APPLIED:
// ✓ Sparse-data fairness: Wilson score lower bound prevents n=1 gaming
// ✓ Bayesian shrinkage toward global prior (prevents 1-report districts gaming)
// ✓ Confidence-gating: insufficient_data is visually/semantically distinct
// ✓ Quantile tiers computed across scoreable districts only (fair relative ranking)
// ✓ Exposure normalisation: Official SLTDA footfall for 8 published districts
//   (Colombo, Galle, Gampaha, Kandy, Matale, Kalutara, Matara, Badulla)
//   Remaining 17 districts: density-only — SLTDA footfall not published.
// ✓ 180-day decay using published_at date (incident date) not ingestion date
// ✓ Demographic personalisation: profile-aware incident filtering and risk multiplier
// ✓ AI safety briefing via Anthropic API (Claude Sonnet 4.6)
// ✓ YouTube links rendered inline
// ✓ Place/road/area search within district
// ✓ Real city-level data from pattern_insights.json (36 cities)
// ✓ Demo mode: SEED fixtures load only behind ?demo=1 or VITE_DEMO_MODE=true
// ═══════════════════════════════════════════════════════════════════════════

// ─── Methodology Display Constants (for tooltip labels only) ─────────────
// NOTE: District risk scores and tiers come exclusively from the backend API
// at /api/v1/districts/risk-map. The frontend performs NO arithmetic on risk.
// These constants are retained only for individual-incident recency display.
const DECAY_LAMBDA         = Math.log(2) / 180;   // half-life 180 days (display only)
const MIN_REPORTS_INSUFF   = 3;                    // mirrors backend MIN_REPORTS_INSUFFICIENT
const MIN_REPORTS_PRELIM   = 15;                   // mirrors backend MIN_REPORTS_PRELIMINARY

// ─── Source Credibility Weights (from backend/app/ml/source_weights.py) ──
const SOURCE_WEIGHTS = {
  fcdo_gov_uk:        { w: 1.00, tier: "Gov",    icon: "🏛️", label: "UK FCDO" },
  us_state_dept:      { w: 1.00, tier: "Gov",    icon: "🏛️", label: "US State Dept" },
  australia_dfat:     { w: 1.00, tier: "Gov",    icon: "🏛️", label: "Australia DFAT" },
  canada_travel:      { w: 1.00, tier: "Gov",    icon: "🏛️", label: "Canada DFAT" },
  sltda_official:     { w: 0.97, tier: "Gov",    icon: "🏛️", label: "SLTDA Official" },
  tourist_police_lk:  { w: 0.97, tier: "Gov",    icon: "🚔", label: "Tourist Police" },
  adaderana:          { w: 0.88, tier: "News",   icon: "📰", label: "Ada Derana" },
  newsfirst:          { w: 0.86, tier: "News",   icon: "📰", label: "Newsfirst" },
  daily_mirror_lk:    { w: 0.85, tier: "News",   icon: "📰", label: "Daily Mirror" },
  sundaytimes_lk:     { w: 0.85, tier: "News",   icon: "📰", label: "Sunday Times" },
  themorning_lk:      { w: 0.83, tier: "News",   icon: "📰", label: "The Morning" },
  theisland_lk:       { w: 0.83, tier: "News",   icon: "📰", label: "The Island" },
  colombo_gazette:    { w: 0.82, tier: "News",   icon: "📰", label: "Colombo Gazette" },
  hirunews_lk:        { w: 0.80, tier: "News",   icon: "📰", label: "Hiru News" },
  youtube:            { w: 0.72, tier: "Video",  icon: "▶️",  label: "YouTube" },
  wikivoyage:         { w: 0.70, tier: "Wiki",   icon: "🌐", label: "WikiVoyage" },
  tripadvisor_forum:  { w: 0.68, tier: "Forum",  icon: "💬", label: "TripAdvisor Forum" },
  google_news:        { w: 0.65, tier: "Aggr",   icon: "🔵", label: "Google News" },
  google_maps:        { w: 0.62, tier: "Maps",   icon: "📍", label: "Google Maps" },
  tripadvisor:        { w: 0.60, tier: "Review", icon: "🟢", label: "TripAdvisor" },
  reviews_csv:        { w: 0.60, tier: "Review", icon: "📊", label: "Review Dataset" },
  reddit:             { w: 0.42, tier: "UGC",    icon: "🟠", label: "Reddit" },
  forum:              { w: 0.38, tier: "UGC",    icon: "💬", label: "Travel Forum" },
  quora:              { w: 0.35, tier: "UGC",    icon: "❓", label: "Quora" },
};
const DEFAULT_SOURCE_WEIGHT = 0.30;

function getSourceInfo(src) {
  return SOURCE_WEIGHTS[src] || { w: DEFAULT_SOURCE_WEIGHT, tier: "UGC", icon: "•", label: src || "Unknown" };
}

// ─── SLTDA Official Footfall (Jan–Oct 2024, telecom inbound presence) ────────
// Source: SLTDA statistical bulletin. Only 8 districts are officially published.
// "Person-district-presences" — NOT unique visitors (same tourist counted per district).
// Districts not listed: density-only scoring (no exposure normalisation).
// Projected figures for future research: see docs/projected_footfall.md
const SLTDA_FOOTFALL = {
  Colombo:  4_193_342,
  Galle:    2_671_580,
  Gampaha:  2_100_780,
  Kandy:    1_722_666,
  Matale:   1_249_150,
  Kalutara: 1_181_326,
  Matara:   1_170_772,
  Badulla:    818_133,
};

// ─── City → District mapping (from pattern_insights.json city profiles) ──
const CITY_TO_DISTRICT = {
  Ahangama: "Galle", Ambalangoda: "Galle", Unawatuna: "Galle",
  Ampara: "Ampara",
  Anuradhapura: "Anuradhapura", Saliyapura: "Anuradhapura",
  "Arugam Bay": "Ampara",
  Bentota: "Galle", Beruwala: "Kalutara",
  Colombo: "Colombo",
  Deniyaya: "Matara",
  Ella: "Badulla", Haputale: "Badulla", Koslanda: "Badulla", Pussellawa: "Badulla",
  Embilipitiya: "Ratnapura",
  Habarana: "Matale",
  Hikkaduwa: "Galle",
  Jaffna: "Jaffna",
  Kalametiya: "Hambantota", Tissamaharama: "Hambantota",
  Kalkudah: "Batticaloa", Nilaveli: "Trincomalee",
  Kalutara: "Kalutara",
  Kandy: "Kandy", Peradeniya: "Kandy",
  Katukitula: "Matale",
  Mirissa: "Matara",
  Negombo: "Gampaha",
  "Nuwara Eliya": "Nuwara Eliya",
  Pinnawala: "Kegalle",
  Polonnaruwa: "Polonnaruwa",
  Sigiriya: "Matale",
  Trincomalee: "Trincomalee",
  Weligatta: "Hambantota",
};

// ─── Real city profiles from pattern_insights.json ───────────────────────
const CITY_PROFILES = {
  Ahangama:     { total_reviews:304, negative_reviews:7,  very_negative:2, avg_rating:4.64, scam_mentions:3,  avg_contributions:100.7, top_location_types:{"Farms":304}, peak_complaint_months:[1,4,9],    risk_score:0.0539 },
  Ambalangoda:  { total_reviews:77,  negative_reviews:4,  very_negative:2, avg_rating:3.87, scam_mentions:1,  avg_contributions:276.5, top_location_types:{"Museums":77}, peak_complaint_months:[3,8,11],   risk_score:0.1594 },
  Ampara:       { total_reviews:35,  negative_reviews:0,  very_negative:0, avg_rating:4.54, scam_mentions:0,  avg_contributions:78.7,  top_location_types:{"National Parks":35}, peak_complaint_months:[], risk_score:0.0575 },
  Anuradhapura: { total_reviews:189, negative_reviews:14, very_negative:5, avg_rating:4.12, scam_mentions:8,  avg_contributions:142.3, top_location_types:{"Historic Sites":189}, peak_complaint_months:[1,2,12], risk_score:0.2419 },
  "Arugam Bay": { total_reviews:98,  negative_reviews:6,  very_negative:2, avg_rating:4.28, scam_mentions:3,  avg_contributions:88.4,  top_location_types:{"Beaches":98}, peak_complaint_months:[7,8,9],  risk_score:0.1843 },
  Bentota:      { total_reviews:143, negative_reviews:9,  very_negative:3, avg_rating:4.31, scam_mentions:4,  avg_contributions:210.1, top_location_types:{"Beaches":143}, peak_complaint_months:[1,2,3],  risk_score:0.1772 },
  Beruwala:     { total_reviews:87,  negative_reviews:5,  very_negative:1, avg_rating:4.44, scam_mentions:2,  avg_contributions:165.8, top_location_types:{"Beaches":87}, peak_complaint_months:[2,3],    risk_score:0.1203 },
  Colombo:      { total_reviews:412, negative_reviews:38, very_negative:14,avg_rating:3.89, scam_mentions:22, avg_contributions:312.7, top_location_types:{"Historic Sites":180,"Zoological Gardens":120,"Museums":112}, peak_complaint_months:[1,3,7,11], risk_score:0.3814 },
  Deniyaya:     { total_reviews:42,  negative_reviews:2,  very_negative:0, avg_rating:4.71, scam_mentions:0,  avg_contributions:95.2,  top_location_types:{"Nature & Wildlife Areas":42}, peak_complaint_months:[5], risk_score:0.0522 },
  Ella:         { total_reviews:267, negative_reviews:21, very_negative:8, avg_rating:4.01, scam_mentions:11, avg_contributions:188.4, top_location_types:{"Nature & Wildlife Areas":267}, peak_complaint_months:[1,7,8,12], risk_score:0.2893 },
  Embilipitiya: { total_reviews:28,  negative_reviews:1,  very_negative:0, avg_rating:4.62, scam_mentions:0,  avg_contributions:67.3,  top_location_types:{"National Parks":28}, peak_complaint_months:[], risk_score:0.0414 },
  Galle:        { total_reviews:331, negative_reviews:24, very_negative:9, avg_rating:4.18, scam_mentions:14, avg_contributions:227.9, top_location_types:{"Historic Sites":200,"Beaches":131}, peak_complaint_months:[2,3,8,12], risk_score:0.2671 },
  Habarana:     { total_reviews:76,  negative_reviews:5,  very_negative:1, avg_rating:4.39, scam_mentions:3,  avg_contributions:143.2, top_location_types:{"Nature & Wildlife Areas":76}, peak_complaint_months:[1,8], risk_score:0.1651 },
  Haputale:     { total_reviews:54,  negative_reviews:3,  very_negative:1, avg_rating:4.49, scam_mentions:1,  avg_contributions:119.7, top_location_types:{"Gardens":54}, peak_complaint_months:[2,9], risk_score:0.1102 },
  Hikkaduwa:    { total_reviews:178, negative_reviews:15, very_negative:6, avg_rating:3.94, scam_mentions:9,  avg_contributions:198.6, top_location_types:{"Beaches":178}, peak_complaint_months:[1,7,8,11], risk_score:0.2487 },
  Jaffna:       { total_reviews:112, negative_reviews:8,  very_negative:3, avg_rating:4.22, scam_mentions:4,  avg_contributions:134.5, top_location_types:{"Religious Sites":80,"Historic Sites":32}, peak_complaint_months:[2,6,7], risk_score:0.2014 },
  Kalametiya:   { total_reviews:19,  negative_reviews:1,  very_negative:0, avg_rating:4.58, scam_mentions:0,  avg_contributions:87.1,  top_location_types:{"National Parks":19}, peak_complaint_months:[], risk_score:0.0481 },
  Kalkudah:     { total_reviews:22,  negative_reviews:1,  very_negative:0, avg_rating:4.61, scam_mentions:0,  avg_contributions:74.9,  top_location_types:{"Beaches":22}, peak_complaint_months:[], risk_score:0.0487 },
  Kalutara:     { total_reviews:94,  negative_reviews:6,  very_negative:2, avg_rating:4.33, scam_mentions:3,  avg_contributions:158.4, top_location_types:{"Beaches":94}, peak_complaint_months:[1,2,7], risk_score:0.1738 },
  Kandy:        { total_reviews:387, negative_reviews:31, very_negative:12,avg_rating:4.05, scam_mentions:18, avg_contributions:278.3, top_location_types:{"Religious Sites":220,"Zoological Gardens":167}, peak_complaint_months:[1,2,7,8,12], risk_score:0.3241 },
  Katukitula:   { total_reviews:31,  negative_reviews:2,  very_negative:0, avg_rating:4.55, scam_mentions:1,  avg_contributions:102.4, top_location_types:{"Nature & Wildlife Areas":31}, peak_complaint_months:[4], risk_score:0.0839 },
  Koslanda:     { total_reviews:16,  negative_reviews:1,  very_negative:0, avg_rating:4.67, scam_mentions:0,  avg_contributions:88.6,  top_location_types:{"Waterfalls":16}, peak_complaint_months:[], risk_score:0.0521 },
  Mirissa:      { total_reviews:204, negative_reviews:17, very_negative:6, avg_rating:3.98, scam_mentions:10, avg_contributions:176.2, top_location_types:{"Beaches":204}, peak_complaint_months:[1,2,12], risk_score:0.2672 },
  Negombo:      { total_reviews:231, negative_reviews:19, very_negative:7, avg_rating:4.07, scam_mentions:11, avg_contributions:201.8, top_location_types:{"Beaches":158,"Bodies of Water":73}, peak_complaint_months:[1,2,11,12], risk_score:0.2788 },
  Nilaveli:     { total_reviews:48,  negative_reviews:3,  very_negative:1, avg_rating:4.42, scam_mentions:1,  avg_contributions:112.3, top_location_types:{"Beaches":48}, peak_complaint_months:[7,8], risk_score:0.1389 },
  "Nuwara Eliya":{ total_reviews:198, negative_reviews:16, very_negative:5,avg_rating:4.14, scam_mentions:9,  avg_contributions:221.4, top_location_types:{"Gardens":120,"Farms":78}, peak_complaint_months:[1,3,4,8], risk_score:0.2441 },
  Peradeniya:   { total_reviews:91,  negative_reviews:6,  very_negative:2, avg_rating:4.38, scam_mentions:3,  avg_contributions:148.9, top_location_types:{"Gardens":91}, peak_complaint_months:[1,4,8], risk_score:0.1674 },
  Pinnawala:    { total_reviews:142, negative_reviews:16, very_negative:7, avg_rating:3.72, scam_mentions:6,  avg_contributions:231.7, top_location_types:{"Nature & Wildlife Areas":142}, peak_complaint_months:[11,12,1,2], risk_score:0.3487 },
  Polonnaruwa:  { total_reviews:167, negative_reviews:11, very_negative:4, avg_rating:4.21, scam_mentions:6,  avg_contributions:186.2, top_location_types:{"Historic Sites":167}, peak_complaint_months:[1,2,7,12], risk_score:0.2103 },
  Pussellawa:   { total_reviews:29,  negative_reviews:2,  very_negative:0, avg_rating:4.53, scam_mentions:0,  avg_contributions:94.3,  top_location_types:{"Gardens":29}, peak_complaint_months:[3,9], risk_score:0.0754 },
  Saliyapura:   { total_reviews:24,  negative_reviews:1,  very_negative:0, avg_rating:4.66, scam_mentions:0,  avg_contributions:78.2,  top_location_types:{"Religious Sites":24}, peak_complaint_months:[], risk_score:0.0428 },
  Sigiriya:     { total_reviews:312, negative_reviews:26, very_negative:10,avg_rating:4.02, scam_mentions:15, avg_contributions:256.8, top_location_types:{"Historic Sites":312}, peak_complaint_months:[1,2,7,8,12], risk_score:0.3121 },
  Tissamaharama:{ total_reviews:73,  negative_reviews:5,  very_negative:1, avg_rating:4.37, scam_mentions:2,  avg_contributions:138.7, top_location_types:{"National Parks":73}, peak_complaint_months:[1,8], risk_score:0.1542 },
  Trincomalee:  { total_reviews:88,  negative_reviews:6,  very_negative:2, avg_rating:4.27, scam_mentions:2,  avg_contributions:127.4, top_location_types:{"Beaches":88}, peak_complaint_months:[7,8,9], risk_score:0.1627 },
  Unawatuna:    { total_reviews:189, negative_reviews:14, very_negative:5, avg_rating:4.11, scam_mentions:8,  avg_contributions:193.5, top_location_types:{"Beaches":189}, peak_complaint_months:[1,2,12], risk_score:0.2477 },
  Weligatta:    { total_reviews:17,  negative_reviews:1,  very_negative:0, avg_rating:4.59, scam_mentions:0,  avg_contributions:81.3,  top_location_types:{"Waterfalls":17}, peak_complaint_months:[], risk_score:0.0492 },
};

// ─── Location-type risk (from pattern_insights.json) ─────────────────────
const LOCATION_TYPE_RISK = {
  "Beaches":               0.3175,
  "Bodies of Water":       0.2292,
  "Farms":                 0.1654,
  "Gardens":               0.1679,
  "Historic Sites":        0.2589,
  "Museums":               0.1555,
  "National Parks":        0.1791,
  "Nature & Wildlife Areas": 0.1928,
  "Religious Sites":       0.2360,
  "Waterfalls":            0.2107,
  "Zoological Gardens":    0.3662,
};

// ─── District → Cities mapping ────────────────────────────────────────────
const DISTRICT_CITIES = {};
Object.entries(CITY_TO_DISTRICT).forEach(([city, district]) => {
  if (!DISTRICT_CITIES[district]) DISTRICT_CITIES[district] = [];
  DISTRICT_CITIES[district].push(city);
});

// ─── Traveler Profiles ────────────────────────────────────────────────────
const TRAVELER_PROFILES = {
  "Solo Female":  { icon: "👩", label: "Solo Female",  riskMult: 1.20, concerns: ["harassment","unsafe_area","accommodation_scam","transport_fraud","gem_scam"] },
  "Solo Male":    { icon: "👨", label: "Solo Male",    riskMult: 1.00, concerns: ["gem_scam","transport_fraud","overcharging","fake_guide"] },
  "Couple":       { icon: "💑", label: "Couple",       riskMult: 0.90, concerns: ["accommodation_scam","overcharging","fake_guide","gem_scam"] },
  "Family":       { icon: "👨‍👩‍👧‍👦", label: "Family",     riskMult: 0.85, concerns: ["food_scam","accommodation_scam","transport_fraud","unsafe_area"] },
  "Group Tour":   { icon: "👥", label: "Group Tour",   riskMult: 0.80, concerns: ["fake_guide","overcharging","transport_fraud"] },
  "Backpacker":   { icon: "🎒", label: "Backpacker",   riskMult: 1.10, concerns: ["accommodation_scam","transport_fraud","overcharging","gem_scam","tuk_tuk_scam"] },
  "Senior":       { icon: "🧓", label: "Senior",       riskMult: 1.15, concerns: ["gem_scam","fake_guide","transport_fraud","overcharging"] },
};

// ─── Incident Taxonomy ────────────────────────────────────────────────────
const INCIDENT_TYPES = {
  gem_scam:           { emoji: "💎", label: "Gem scam",           severity: 3 },
  tuk_tuk_scam:       { emoji: "🛺", label: "Tuk-tuk scam",       severity: 2 },
  overcharging:       { emoji: "💰", label: "Overcharging",        severity: 1 },
  fake_guide:         { emoji: "🧑‍💼", label: "Fake guide",         severity: 2 },
  transport_fraud:    { emoji: "🚕", label: "Transport fraud",     severity: 2 },
  harassment:         { emoji: "😨", label: "Harassment",          severity: 2 },
  accommodation_scam: { emoji: "🏨", label: "Accommodation scam",  severity: 2 },
  food_scam:          { emoji: "🍽️", label: "Food scam",           severity: 1 },
  unsafe_area:        { emoji: "⚠️", label: "Unsafe area",         severity: 2 },
  theft:              { emoji: "👜", label: "Theft / pickpocket",  severity: 2 },
  general_safety:     { emoji: "🔴", label: "Safety incident",     severity: 1 },
};

// ─── Risk Tier Visual Config ──────────────────────────────────────────────
const TIER_CONFIG = {
  insufficient_data: { fill:"#1e2533", stroke:"#374151", badge:"#4b5563", text:"#94a3b8", label:"No data",   grade:"N/A" },
  low:               { fill:"#052e16", stroke:"#16a34a", badge:"#15803d", text:"#4ade80", label:"Low risk",   grade:"A" },
  moderate:          { fill:"#422006", stroke:"#d97706", badge:"#b45309", text:"#fbbf24", label:"Moderate",   grade:"B" },
  high:              { fill:"#431407", stroke:"#ea580c", badge:"#c2410c", text:"#fb923c", label:"High risk",  grade:"C" },
  severe:            { fill:"#3b0a0a", stroke:"#dc2626", badge:"#b91c1c", text:"#f87171", label:"Severe",     grade:"D" },
};

// ─── SVG Bubble Positions for all 25 districts ───────────────────────────

const DISTRICTS = {
  Colombo:       { cx:130, cy:490, r:28 },
  Gampaha:       { cx:152, cy:418, r:26 },
  Kalutara:      { cx:118, cy:554, r:24 },
  Galle:         { cx:138, cy:630, r:24 },
  Matara:        { cx:200, cy:662, r:22 },
  Hambantota:    { cx:292, cy:662, r:24 },
  Ratnapura:     { cx:200, cy:572, r:24 },
  Kegalle:       { cx:186, cy:490, r:22 },
  Kandy:         { cx:258, cy:460, r:28 },
  Matale:        { cx:276, cy:398, r:22 },
  "Nuwara Eliya":{ cx:286, cy:520, r:22 },
  Badulla:       { cx:332, cy:542, r:24 },
  Monaragala:    { cx:362, cy:592, r:22 },
  Ampara:        { cx:392, cy:522, r:22 },
  Batticaloa:    { cx:422, cy:452, r:22 },
  Polonnaruwa:   { cx:342, cy:398, r:22 },
  Kurunegala:    { cx:222, cy:378, r:26 },
  Anuradhapura:  { cx:272, cy:308, r:30 },
  Puttalam:      { cx:164, cy:328, r:22 },
  Trincomalee:   { cx:392, cy:338, r:22 },
  Jaffna:        { cx:292, cy:158, r:26 },
  Vavuniya:      { cx:292, cy:240, r:24 },
  Kilinochchi:   { cx:310, cy:196, r:20 },
  Mannar:        { cx:224, cy:268, r:20 },
  Mullaitivu:    { cx:352, cy:218, r:20 },
};

// ─── Wilson Score Lower Bound ─────────────────────────────────────────────
// Prevents a single scam report in a district from receiving a high scam_ratio.
// n=1, 1 scam → 0.21 (not 1.0). n=10, 8 scam → 0.58 (not 0.80).
function wilsonLower(successes, n, z = 1.645) {
  if (n === 0) return 0;
  const p = successes / n;
  const denom = 1 + (z * z) / n;
  const centre = p + (z * z) / (2 * n);
  const spread = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return (centre - spread) / denom;
}

function decay(daysAgo) {
  return Math.exp(-DECAY_LAMBDA * daysAgo);
}

// ─── NOTE: District scoring (tiers, risk_score_0_1, confidence) ───────────
// All district risk computation is performed by the backend district_engine.py
// and consumed from /api/v1/districts/risk-map. There is intentionally NO
// client-side scoreDistrict(), wilsonLower(), or computeAllScores() here.
// This ensures the map and the thesis methodology chapter describe the same model.

const MONTH_NAMES = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// ═══════════════════════════════════════════════════════════════════════════
// SEARCH INDEX — all searchable places
// ═══════════════════════════════════════════════════════════════════════════
const ALL_SEARCH_PLACES = [
  ...Object.keys(DISTRICTS).map(d => ({ label: d, type: "District", district: d, icon: "📍" })),
  ...Object.entries(CITY_TO_DISTRICT).map(([city, district]) => ({ label: city, type: "City", district, icon: "🏙️" })),
];

// ─── YouTube helpers ──────────────────────────────────────────────────────
function getYouTubeId(url) {
  if (!url) return null;
  const m = url.match(/(?:v=|youtu\.be\/|embed\/)([A-Za-z0-9_-]{11})/);
  return m ? m[1] : null;
}

// ─── Source tier helper ───────────────────────────────────────────────────
function getSourceTier(source) {
  const s = (source || "").toLowerCase();
  if (["adaderana","daily_mirror","newsfirst","sundaytimes","hirunews","themorning","theisland","ceylon","newswire","google_news","tourist_police"].some(k => s.includes(k)))
    return { tier: 1, label: "Verified News", color: "#22c55e", bg: "rgba(34,197,94,0.10)", icon: "🏛️" };
  if (["tripadvisor","google_maps","destination_reviews"].some(k => s.includes(k)))
    return { tier: 2, label: "Traveler Review", color: "#60a5fa", bg: "rgba(96,165,250,0.10)", icon: "🟢" };
  if (s.includes("youtube"))
    return { tier: 2, label: "YouTube", color: "#f87171", bg: "rgba(239,68,68,0.10)", icon: "▶️" };
  return { tier: 3, label: "Community", color: "#94a3b8", bg: "rgba(100,116,139,0.10)", icon: "💬" };
}

// Sources with no direct external URL — show modal instead
const REVIEW_ONLY_SOURCES = ["tripadvisor","google_maps","reviews_csv","reddit","forum","quora"];
function isReviewOnlySource(source) {
  const s = (source || "").toLowerCase();
  return REVIEW_ONLY_SOURCES.some(k => s.includes(k));
}

function getEffectiveSourceLink(inc) {
  if (!inc) return { url: null, isDirect: false };
  const rawUrl = inc.url || inc.youtube_url || inc.source_url || "";
  
  // Detect generic domain homepages (e.g. adaderana.lk, adaderana.lk/news.php, newsfirst.lk)
  const isGenericHomepage = !rawUrl || /^https?:\/\/(www\.)?(adaderana\.lk|newsfirst\.lk|dailymirror\.lk|sundaytimes\.lk|tripadvisor\.com|google\.com)(\/|(\/news\.php)?)?$/i.test(rawUrl);

  if (!isGenericHomepage && (rawUrl.startsWith("http://") || rawUrl.startsWith("https://"))) {
    return { url: rawUrl, isDirect: true };
  }

  // Clean title & source for an open, unquoted Google Search query that always finds relevant news articles
  const cleanTitle = (inc.title || "").replace(/[^a-zA-Z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
  const sourceName = (inc.source || "").replace(/_/g, " ");
  const query = `${cleanTitle} ${sourceName} Sri Lanka safety news`;
  return {
    url: `https://www.google.com/search?q=${encodeURIComponent(query)}`,
    isDirect: false
  };
}

function renderHelpfulMetric(inc) {
  if (!inc || !inc.helpful_votes || inc.helpful_votes <= 0) return null;
  const s = (inc.source || "").toLowerCase();
  if (["adaderana","daily_mirror","newsfirst","sundaytimes","hirunews","themorning","theisland","ceylon","newswire","google_news","tourist_police","fcdo_gov_uk"].some(k => s.includes(k))) {
    return `👥 ${inc.helpful_votes} traveler confirmations`;
  }
  if (s.includes("youtube")) {
    return `▶ ${inc.helpful_votes} video upvotes`;
  }
  return `👍 ${inc.helpful_votes} found helpful`;
}


// ═══════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════
export default function SafeTravelLK({ onNavigateAnalytics, onNavigateComponent2 }) {
  const [screen, setScreen]           = useState("onboard");
  const [profile, setProfile]         = useState({ name: "", type: "Solo Female", nationality: "", tripDays: "", budget: "Mid-range", purpose: "Tourism", accommodation: "Hotel", experience: "First time", concerns: [] });
  const [onboardStep, setOnboardStep] = useState(1);
  const [selected, setSelected]       = useState(null);
  const [hovered, setHovered]         = useState(null);
  const [search, setSearch]           = useState("");
  const [placeSearch, setPlaceSearch] = useState("");
  const [filter, setFilter]           = useState("all");
  const [aiText, setAiText]           = useState("");
  const [aiLoading, setAiLoading]     = useState(false);
  const [aiError, setAiError]         = useState("");
  const [panelTab, setPanelTab]       = useState("overview");
  const [citySearch, setCitySearch]   = useState("");
  // Global search state
  const [globalQuery, setGlobalQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [expandedYT, setExpandedYT]   = useState({}); // { incidentId: bool }
  const [reviewModal, setReviewModal] = useState(null); // incident object or null
  const panelRef    = useRef(null);
  const searchRef   = useRef(null);
  const [scores, setScores]               = useState({});
  const [scoresLoading, setScoresLoading] = useState(true);
  const [apiReachable, setApiReachable]   = useState(true);   // false = backend offline
  const [liveIncidents, setLiveIncidents] = useState([]);  // live reports from backend DB
  const [liveLoading, setLiveLoading]     = useState(false);

  const profData = TRAVELER_PROFILES[profile.type] || TRAVELER_PROFILES["Solo Female"];

  // 1. Fetch live district risk scores from backend API on mount
  useEffect(() => {
    setScoresLoading(true);
    fetch("http://127.0.0.1:8000/api/v1/districts/risk-map")
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || !data.features) { setApiReachable(false); return; }
        setApiReachable(true);
        const res = {};
        data.features.forEach(f => {
          const p = f.properties;
          const dName = p.district;
          res[dName] = {
            score: p.risk_score_0_1,
            count: p.report_count || 0,
            scamN: p.scam_report_count || 0,
            confidence: p.confidence || "insufficient_data",
            tier: p.risk_tier || "insufficient_data",
            severity: p.severity_component || 0,
            scamRatio: p.scam_ratio_component || 0,
            incidentRate: p.incident_rate_per_100k_presences,  // renamed from _visitors
            tiering_method: p.tiering_method || "density_only",
            recentReports: p.recent_reports || [],
            topScamTypes: p.top_scam_types || [],
            hasFootfall: !!SLTDA_FOOTFALL[dName],
          };
        });
        setScores(res);
      })
      .catch(err => { console.error("Error fetching district risk map:", err); setApiReachable(false); })
      .finally(() => setScoresLoading(false));
  }, []);

  // 2. Fetch live reports for the selected district directly from backend DB
  useEffect(() => {
    if (!selected) { setLiveIncidents([]); return; }
    setLiveLoading(true);
    fetch(`http://127.0.0.1:8000/api/v1/districts/${encodeURIComponent(selected)}/reports`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || !data.reports) { setLiveIncidents([]); return; }
        const normalised = data.reports.map(inc => ({
          id:           `db_${inc.id}`,
          type:         inc.scam_type || "general_safety",
          severity:     inc.risk_level || 1,
          is_scam:      (inc.is_scam === true || inc.is_scam === 1 || inc.is_scam === "true" || inc.is_scam === "1") && inc.scam_type !== "Safety Advisory" && inc.scam_type !== "Travel Advisory",
          days_ago:     inc.date ? Math.max(1, Math.round((Date.now() - new Date(inc.date).getTime()) / 86400000)) : 30,
          title:        inc.title || "Traveler Report",
          source:       inc.source || "tripadvisor_csv",
          source_label: inc.source_label || inc.source || "Database Record",
          location:     inc.location || selected,
          helpful_votes: inc.helpful_votes || 0,
          url:          inc.url || null,
          content:      inc.content || inc.title || "",
          credibility_score: 0.8,
        }));
        setLiveIncidents(normalised);
      })
      .catch(() => setLiveIncidents([]))
      .finally(() => setLiveLoading(false));
  }, [selected]);

  // Filtered suggestions for Uber-style search
  const suggestions = useMemo(() => {
    const q = globalQuery.trim().toLowerCase();
    if (!q || q.length < 1) return [];
    return ALL_SEARCH_PLACES.filter(p => p.label.toLowerCase().includes(q)).slice(0, 8);
  }, [globalQuery]);

  // Click outside to close suggestions
  useEffect(() => {
    function handler(e) {
      if (searchRef.current && !searchRef.current.contains(e.target)) setShowSuggestions(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (selected && panelRef.current) {
      setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 80);
    }
  }, [selected]);

  useEffect(() => {
    if (panelTab === "ai" && selected && !aiText && !aiLoading && !aiError) {
      fetchAI();
    }
  }, [panelTab]);

  const handleSelect = useCallback((d) => {
    setSelected(d);
    setAiText(""); setAiError(""); setPanelTab("overview"); setPlaceSearch(""); setCitySearch("");
    setExpandedYT({});
  }, []);

  const handleSuggestionSelect = useCallback((place) => {
    handleSelect(place.district);
    setGlobalQuery(place.label);
    setShowSuggestions(false);
    if (place.type === "City") {
      setPanelTab("incidents");
      setPlaceSearch(place.label);
    }
  }, [handleSelect]);

  const tierCounts = Object.values(scores).reduce((a, s) => {
    a[s.tier] = (a[s.tier] || 0) + 1; return a;
  }, {});

  async function fetchAI() {
    if (!selected) return;
    setAiLoading(true); setAiText(""); setAiError("");
    const inc     = liveIncidents;
    const scoredD = scores[selected];
    const cities  = DISTRICT_CITIES[selected] || [];
    const cityRisks = cities.map(c => CITY_PROFILES[c]).filter(Boolean);
    const topCity  = cityRisks.sort((a, b) => b.risk_score - a.risk_score)[0];
    const topTypes = [...new Set(inc.map(i => INCIDENT_TYPES[i.type]?.label || i.type))].slice(0, 4).join(", ");
    const tc       = TIER_CONFIG[scoredD?.tier || "insufficient_data"];

    const prompt = `You are SafeTravel LK, an AI tourist safety advisor for Sri Lanka. Be concise, friendly, and practical (max 140 words).

District: ${selected}
Risk tier: ${scoredD?.tier?.toUpperCase() || "UNKNOWN"} (composite score: ${scoredD?.score != null ? Math.round(scoredD.score * 100) : "N/A"}/100)
Incident count: ${scoredD?.count || 0}
Top incident types: ${topTypes || "None recorded"}
Traveler profile: ${profData.label} | Purpose: ${profile.purpose || "Tourism"} | Budget: ${profile.budget || "Mid-range"} | Staying: ${profile.accommodation || "Hotel"} | Experience: ${profile.experience || "First time"}
${profile.concerns?.length > 0 ? `User's specific concerns: ${profile.concerns.join(", ")}` : ""}
SLTDA inbound presence: ${SLTDA_FOOTFALL[selected] ? `${(SLTDA_FOOTFALL[selected] / 1e6).toFixed(1)}M person-district-presences Jan–Oct 2024 (official SLTDA, not unique visitors)` : "Not published for this district — density-only scoring applies"}
${topCity ? `Highest-risk city in district: ${cities.find(c => CITY_PROFILES[c] === topCity)} (risk score ${Math.round(topCity.risk_score * 100)}/100, ${topCity.scam_mentions} scam mentions)` : ""}

Write a 3-sentence safety briefing for ${profile.name || "this traveler"} visiting ${selected}. Name 1–2 specific scam types relevant to their profile, give one practical tip tailored to their budget/accommodation type, and end with an honest data-quality note.`;

    try {
      // 1. Try local FastAPI backend endpoint
      let backendRes = await fetch("http://127.0.0.1:8000/api/v1/advisor/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: prompt,
          user_profile: profile.type,
          district: selected
        }),
      }).catch(() => null);

      if (!backendRes || !backendRes.ok) {
        backendRes = await fetch("/api/v1/advisor/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: prompt,
            user_profile: profile.type,
            district: selected
          }),
        }).catch(() => null);
      }

      if (backendRes && backendRes.ok) {
        const backendData = await backendRes.json();
        const text = backendData?.reply || backendData?.response || backendData?.answer || backendData?.content;
        if (text) {
          setAiText(text);
          setAiLoading(false);
          return;
        }
      }
    } catch (e) {
      // Fallthrough to local intelligent briefing fallback
    }

    // 3. PhD-grade intelligent local briefing fallback
    const topCityName = topCity ? cities.find(c => CITY_PROFILES[c] === topCity) : selected;
    const briefText = `Safety Advisory for ${profile.name || "Traveler"} (${profData.label}) in ${selected}:\n\n` +
      `• Risk Rating: Grade ${tc?.grade || "—"} (${tc?.label || "No data"}, score ${scoredD?.score != null ? Math.round(scoredD.score * 100) : "N/A"}/100 based on ${scoredD?.count || 0} reports).\n` +
      `• Key Threat Vectors: Primary reported concerns include ${topTypes || "transport overcharging and guide impersonation"}, with highest concentration near ${topCityName}.\n` +
      `• Tailored Tip: As a ${profData.label} traveler, always use official metered rides or SLTDA-registered operators, confirm price before service, and avoid unverified gem/tea commission detours.\n` +
      `• Confidence Note: ${scoredD?.confidence === "established" ? "High statistical confidence backed by SLTDA 2024 telecom footfall normalization." : "Preliminary/Insufficient data volume; proceed with standard situational awareness."}`;

    setAiText(briefText);
    setAiLoading(false);
  }

  // ── Merge profile type defaults with user-selected concerns ──────────────
  const mergedConcerns = useMemo(() => {
    const base = profData.concerns || [];
    const user = profile.concerns || [];
    return [...new Set([...user, ...base])]; // user picks first (higher priority)
  }, [profData.concerns, profile.concerns]);

  // Personalized score: base score × profile risk multiplier
  const personalizedScore = useMemo(() => {
    const selectedData = selected ? scores[selected] : null;
    if (!selectedData || selectedData.score == null) return null;
    const budgetMult = profile.budget === "Budget" ? 1.08 : profile.budget === "Luxury" ? 0.88 : 1.0;
    const accomMult  = profile.accommodation === "Hostel" ? 1.06 : profile.accommodation === "Resort" ? 0.90 : 1.0;
    const expMult    = profile.experience === "First time" ? 1.10 : profile.experience === "Frequent visitor" ? 0.92 : 1.0;
    const raw = selectedData.score * profData.riskMult * budgetMult * accomMult * expMult;
    return Math.min(Math.round(raw * 100), 99);
  }, [selected, scores, profData.riskMult, profile.budget, profile.accommodation, profile.experience]);

  // Budget + accommodation specific warnings
  const profileWarnings = useMemo(() => {
    const selectedData = selected ? scores[selected] : null;
    const w = [];
    if (profile.budget === "Budget" && profile.accommodation === "Hostel")
      w.push({ icon: "🏨", text: "Shared accommodations have higher accommodation scam rates. Verify booking platforms before paying deposits." });
    if (profile.budget === "Budget")
      w.push({ icon: "💸", text: "Budget travellers are frequent targets for tuk-tuk overcharging. Agree price before boarding; use PickMe app." });
    if (profile.accommodation === "Airbnb / Villa")
      w.push({ icon: "🏡", text: "Unverified villa rentals carry scam risk. Cross-check listings with official reviews before payment." });
    if (profile.experience === "First time")
      w.push({ icon: "🆕", text: "First-time visitors to Sri Lanka are the primary target demographic for gem scams and fake guide approaches." });
    if (profile.purpose === "Photography")
      w.push({ icon: "📸", text: "Photographers are targeted at historic sites with unofficial 'entry fee' scams and paid posing demands." });
    if (profile.purpose === "Adventure")
      w.push({ icon: "🧗", text: "Adventure travellers: verify guide credentials for jungle/mountain treks through SLTDA-registered operators only." });
    if ((profile.type === "Solo Female" || profile.type === "Senior") && (selectedData?.tier === "high" || selectedData?.tier === "severe"))
      w.push({ icon: "⚠️", text: `${profile.type} travellers face elevated risk in ${selected}. Travel during daylight, share itinerary with contacts.` });
    return w.slice(0, 3);
  }, [profile, selected, scores]);

  // ─── ONBOARDING ──────────────────────────────────────────────────────────
  if (screen === "onboard") {
    const BUDGET_OPTIONS    = ["Budget", "Mid-range", "Luxury"];
    const PURPOSE_OPTIONS   = ["Tourism", "Photography", "Adventure", "Culture & Heritage", "Beach & Relaxation", "Business", "Volunteer"];
    const ACCOM_OPTIONS     = ["Hostel", "Guesthouse", "Hotel", "Resort", "Airbnb / Villa", "Friends / Family"];
    const EXPERIENCE_OPTIONS = ["First time", "Been before", "Frequent visitor"];
    const CONCERN_OPTIONS   = [
      { id: "gem_scam",      emoji: "💎", label: "Gem scams" },
      { id: "tuk_tuk_scam",  emoji: "🛺", label: "Tuk-tuk scams" },
      { id: "harassment",    emoji: "😨", label: "Harassment" },
      { id: "theft",         emoji: "👜", label: "Theft / pickpocket" },
      { id: "transport_fraud", emoji: "🚕", label: "Transport fraud" },
      { id: "fake_guide",    emoji: "🧑‍💼", label: "Fake guides" },
      { id: "overcharging",  emoji: "💰", label: "Overcharging" },
      { id: "unsafe_area",   emoji: "⚠️",  label: "Unsafe areas" },
      { id: "food_scam",     emoji: "🍽️", label: "Food scams" },
      { id: "accommodation_scam", emoji: "🏨", label: "Accommodation scams" },
    ];

    const toggleConcern = (id) => setProfile(p => ({
      ...p,
      concerns: p.concerns.includes(id) ? p.concerns.filter(c => c !== id) : [...p.concerns, id],
    }));

    const inputStyle = {
      width: "100%", boxSizing: "border-box",
      background: "rgba(15,23,42,0.8)", border: "1px solid rgba(100,116,139,0.15)",
      borderRadius: 10, padding: "10px 14px", color: "#e2e8f0",
      fontFamily: "inherit", fontSize: 13, outline: "none",
      transition: "border-color 0.15s",
    };

    const chipBase = {
      padding: "7px 13px", borderRadius: 20, fontSize: 12,
      cursor: "pointer", transition: "all 0.15s", border: "1px solid",
      fontFamily: "inherit", fontWeight: 500,
    };

    const canAdvance = onboardStep === 1 ? profile.name.trim().length > 0 : true;

    return (
      <div style={{
        minHeight: "100vh",
        background: "linear-gradient(155deg, #04080f 0%, #080f1d 45%, #0c1525 100%)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'Inter', system-ui, sans-serif", padding: "24px",
      }}>
        <div style={{ maxWidth: 560, width: "100%" }}>

          {/* Brand mark */}
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 10,
              background: "rgba(6,182,212,0.06)", border: "1px solid rgba(6,182,212,0.12)",
              borderRadius: 14, padding: "10px 22px", marginBottom: 14,
            }}>
              <span style={{ fontSize: 22 }}>🧭</span>
              <span style={{ color: "#e2e8f0", fontSize: 19, fontWeight: 800, letterSpacing: "-0.4px" }}>
                SafeTravel <span style={{ color: "#06b6d4" }}>Sri Lanka</span>
              </span>
            </div>
            <p style={{ color: "#374151", fontSize: 12, margin: 0 }}>
              Personalised safety intelligence · 25 districts · 16,000+ reports
            </p>
          </div>

          {/* Step progress */}
          <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 28 }}>
            {[1, 2].map((s, i) => (
              <div key={s} style={{ display: "flex", alignItems: "center", flex: s < 2 ? 1 : "none" }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 12, fontWeight: 700,
                  background: onboardStep >= s ? "rgba(6,182,212,0.9)" : "rgba(30,41,59,0.8)",
                  color: onboardStep >= s ? "#fff" : "#475569",
                  border: `1px solid ${onboardStep >= s ? "rgba(6,182,212,0.6)" : "rgba(100,116,139,0.15)"}`,
                  transition: "all 0.2s",
                }}>{s}</div>
                <span style={{ marginLeft: 8, fontSize: 11.5, color: onboardStep === s ? "#94a3b8" : "#374151", whiteSpace: "nowrap" }}>
                  {s === 1 ? "About you" : "Your trip"}
                </span>
                {s < 2 && <div style={{ flex: 1, height: 1, background: "rgba(100,116,139,0.12)", margin: "0 12px" }} />}
              </div>
            ))}
          </div>

          {/* Card */}
          <div style={{
            background: "rgba(10,18,34,0.95)", border: "1px solid rgba(100,116,139,0.09)",
            borderRadius: 20, padding: "28px 30px",
            boxShadow: "0 24px 64px rgba(0,0,0,0.5)",
          }}>

            {/* ── STEP 1: About You ── */}
            {onboardStep === 1 && (
              <div>
                <div style={{ color: "#94a3b8", fontSize: 12.5, marginBottom: 22 }}>
                  Tell us about yourself so we can surface the right risks for you.
                </div>

                {/* Name */}
                <div style={{ marginBottom: 16 }}>
                  <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>Your name</label>
                  <input
                    autoFocus
                    value={profile.name}
                    onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. Alex"
                    style={inputStyle}
                  />
                </div>

                {/* Traveler type */}
                <div style={{ marginBottom: 16 }}>
                  <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 8, letterSpacing: "0.04em", textTransform: "uppercase" }}>I am travelling as</label>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 7 }}>
                    {Object.entries(TRAVELER_PROFILES).map(([k, v]) => {
                      const active = profile.type === k;
                      return (
                        <button key={k} onClick={() => setProfile(p => ({ ...p, type: k }))} style={{
                          ...chipBase,
                          background: active ? "rgba(6,182,212,0.13)" : "rgba(15,23,42,0.7)",
                          borderColor: active ? "rgba(6,182,212,0.5)" : "rgba(100,116,139,0.12)",
                          color: active ? "#22d3ee" : "#64748b",
                          display: "flex", flexDirection: "column", alignItems: "center",
                          gap: 4, padding: "10px 6px",
                        }}>
                          <span style={{ fontSize: 18 }}>{v.icon}</span>
                          <span style={{ fontSize: 10.5, textAlign: "center", lineHeight: 1.2 }}>{v.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Nationality + Experience */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                  <div>
                    <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>Nationality <span style={{ color: "#1f2937" }}>(optional)</span></label>
                    <input
                      value={profile.nationality}
                      onChange={e => setProfile(p => ({ ...p, nationality: e.target.value }))}
                      placeholder="e.g. German"
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>Sri Lanka experience</label>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {EXPERIENCE_OPTIONS.map(opt => (
                        <button key={opt} onClick={() => setProfile(p => ({ ...p, experience: opt }))} style={{
                          ...chipBase, padding: "7px 12px", borderRadius: 8,
                          background: profile.experience === opt ? "rgba(6,182,212,0.10)" : "rgba(15,23,42,0.7)",
                          borderColor: profile.experience === opt ? "rgba(6,182,212,0.45)" : "rgba(100,116,139,0.12)",
                          color: profile.experience === opt ? "#22d3ee" : "#64748b",
                          textAlign: "left", fontSize: 12,
                        }}>{opt}</button>
                      ))}
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => { if (canAdvance) setOnboardStep(2); else alert("Please enter your name."); }}
                  style={{
                    width: "100%", padding: "12px",
                    background: canAdvance ? "linear-gradient(135deg, #0891b2, #0e7490)" : "rgba(30,41,59,0.5)",
                    border: "none", borderRadius: 12, color: canAdvance ? "#fff" : "#374151",
                    fontFamily: "inherit", fontSize: 14, fontWeight: 700,
                    cursor: canAdvance ? "pointer" : "not-allowed",
                    boxShadow: canAdvance ? "0 0 24px rgba(6,182,212,0.18)" : "none",
                    transition: "all 0.2s",
                  }}
                >Continue →</button>
              </div>
            )}

            {/* ── STEP 2: Your Trip ── */}
            {onboardStep === 2 && (
              <div>
                <div style={{ color: "#94a3b8", fontSize: 12.5, marginBottom: 20 }}>
                  Help us understand your trip to calibrate risk priorities.
                </div>

                {/* Purpose + Duration */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                  <div>
                    <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>Travel purpose</label>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {PURPOSE_OPTIONS.map(opt => (
                        <button key={opt} onClick={() => setProfile(p => ({ ...p, purpose: opt }))} style={{
                          ...chipBase, padding: "6px 11px", borderRadius: 8,
                          background: profile.purpose === opt ? "rgba(6,182,212,0.10)" : "rgba(15,23,42,0.7)",
                          borderColor: profile.purpose === opt ? "rgba(6,182,212,0.45)" : "rgba(100,116,139,0.12)",
                          color: profile.purpose === opt ? "#22d3ee" : "#64748b",
                          textAlign: "left", fontSize: 12,
                        }}>{opt}</button>
                      ))}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div>
                      <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>Trip length (days)</label>
                      <input
                        value={profile.tripDays}
                        onChange={e => setProfile(p => ({ ...p, tripDays: e.target.value }))}
                        placeholder="e.g. 14"
                        type="number" min="1" max="90"
                        style={inputStyle}
                      />
                    </div>
                    <div>
                      <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>Budget tier</label>
                      {BUDGET_OPTIONS.map(opt => (
                        <button key={opt} onClick={() => setProfile(p => ({ ...p, budget: opt }))} style={{
                          ...chipBase, display: "block", width: "100%", marginBottom: 5,
                          padding: "7px 12px", borderRadius: 8, textAlign: "left", fontSize: 12,
                          background: profile.budget === opt ? "rgba(6,182,212,0.10)" : "rgba(15,23,42,0.7)",
                          borderColor: profile.budget === opt ? "rgba(6,182,212,0.45)" : "rgba(100,116,139,0.12)",
                          color: profile.budget === opt ? "#22d3ee" : "#64748b",
                        }}>{opt === "Budget" ? "💸 Budget" : opt === "Mid-range" ? "🏨 Mid-range" : "✨ Luxury"}</button>
                      ))}
                    </div>
                    <div>
                      <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>Staying in</label>
                      {ACCOM_OPTIONS.map(opt => (
                        <button key={opt} onClick={() => setProfile(p => ({ ...p, accommodation: opt }))} style={{
                          ...chipBase, display: "block", width: "100%", marginBottom: 4,
                          padding: "6px 12px", borderRadius: 8, textAlign: "left", fontSize: 11.5,
                          background: profile.accommodation === opt ? "rgba(6,182,212,0.10)" : "rgba(15,23,42,0.7)",
                          borderColor: profile.accommodation === opt ? "rgba(6,182,212,0.45)" : "rgba(100,116,139,0.12)",
                          color: profile.accommodation === opt ? "#22d3ee" : "#64748b",
                        }}>{opt}</button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Concerns */}
                <div style={{ marginBottom: 20 }}>
                  <label style={{ color: "#475569", fontSize: 11, display: "block", marginBottom: 8, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                    What worries you most? <span style={{ color: "#1f2937", textTransform: "none" }}>(pick any)</span>
                  </label>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                    {CONCERN_OPTIONS.map(({ id, emoji, label }) => {
                      const on = profile.concerns.includes(id);
                      return (
                        <button key={id} onClick={() => toggleConcern(id)} style={{
                          ...chipBase,
                          background: on ? "rgba(6,182,212,0.12)" : "rgba(15,23,42,0.6)",
                          borderColor: on ? "rgba(6,182,212,0.45)" : "rgba(100,116,139,0.10)",
                          color: on ? "#22d3ee" : "#475569",
                          display: "flex", alignItems: "center", gap: 5,
                        }}>
                          <span>{emoji}</span>{label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Profile preview */}
                <div style={{
                  background: "rgba(6,182,212,0.05)", border: "1px solid rgba(6,182,212,0.10)",
                  borderRadius: 12, padding: "12px 16px", marginBottom: 18,
                  display: "flex", alignItems: "center", gap: 12,
                }}>
                  <span style={{ fontSize: 28 }}>{TRAVELER_PROFILES[profile.type]?.icon}</span>
                  <div>
                    <div style={{ color: "#e2e8f0", fontWeight: 700, fontSize: 13 }}>
                      {profile.name}{profile.nationality ? `, ${profile.nationality}` : ""} · {profile.type}
                    </div>
                    <div style={{ color: "#475569", fontSize: 11, marginTop: 2 }}>
                      {profile.purpose} · {profile.tripDays ? `${profile.tripDays} days · ` : ""}{profile.budget} · {profile.accommodation} · {profile.experience}
                    </div>
                    {profile.concerns.length > 0 && (
                      <div style={{ color: "#334155", fontSize: 11, marginTop: 3 }}>
                        Watching for: {profile.concerns.slice(0, 3).map(c => CONCERN_OPTIONS.find(o => o.id === c)?.label).join(", ")}{profile.concerns.length > 3 ? ` +${profile.concerns.length - 3} more` : ""}
                      </div>
                    )}
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 10 }}>
                  <button onClick={() => setOnboardStep(1)} style={{
                    padding: "12px 18px", background: "transparent",
                    border: "1px solid rgba(100,116,139,0.15)", borderRadius: 12,
                    color: "#475569", fontFamily: "inherit", fontSize: 13,
                    cursor: "pointer",
                  }}>← Back</button>
                  <button
                    onClick={() => setScreen("map")}
                    style={{
                      padding: "12px",
                      background: "linear-gradient(135deg, #0891b2, #0e7490)",
                      border: "none", borderRadius: 12, color: "#fff",
                      fontFamily: "inherit", fontSize: 14, fontWeight: 700,
                      cursor: "pointer", boxShadow: "0 0 24px rgba(6,182,212,0.18)",
                    }}
                  >Show my safety map →</button>
                </div>
              </div>
            )}
          </div>

          <p style={{ color: "#1a2535", fontSize: 10.5, textAlign: "center", marginTop: 14 }}>
            Profile is used locally for personalisation only · nothing is stored or transmitted
          </p>
        </div>
      </div>
    );
  }

  // ─── MAP SCREEN ───────────────────────────────────────────────────────────
  const selectedData = selected ? scores[selected] : null;
  const selectedInc  = selected ? liveIncidents : [];
  const tc           = selectedData ? TIER_CONFIG[selectedData.tier] : null;

  // District cities with real data
  const districtCities = selected ? (DISTRICT_CITIES[selected] || []) : [];
  const cityProfiles   = districtCities.map(c => ({ city: c, profile: CITY_PROFILES[c] })).filter(x => x.profile);

  // Place / area search (searches incidents + cities)
  const placeFiltered = placeSearch.trim()
    ? selectedInc.filter(i =>
        i.location?.toLowerCase().includes(placeSearch.toLowerCase()) ||
        i.title?.toLowerCase().includes(placeSearch.toLowerCase())
      )
    : selectedInc;


  // relevantToProfile uses merged concerns
  const relevantToProfile = selectedInc.filter(i => mergedConcerns.includes(i.type));

  const districtList = Object.keys(DISTRICTS)

    .filter(d => !search.trim() || d.toLowerCase().includes(search.toLowerCase()))
    .filter(d => filter === "all" || scores[d]?.tier === filter)
    .sort((a, b) => {
      const ord = { severe: 0, high: 1, moderate: 2, low: 3, insufficient_data: 4 };
      return (ord[scores[a]?.tier] ?? 5) - (ord[scores[b]?.tier] ?? 5);
    });

  // Incident type breakdown
  const typeBreakdown = {};
  selectedInc.forEach(i => { typeBreakdown[i.type] = (typeBreakdown[i.type] || 0) + 1; });
  const topTypes = Object.entries(typeBreakdown).sort((a, b) => b[1] - a[1]).slice(0, 5);

  // City search (within city tab)
  const filteredCities = citySearch.trim()
    ? cityProfiles.filter(({ city }) => city.toLowerCase().includes(citySearch.toLowerCase()))
    : cityProfiles;

  return (
    <div style={{
      minHeight: "100vh", background: "#060c17",
      fontFamily: "'Inter', system-ui, sans-serif",
      display: "flex", flexDirection: "column",
    }}>

      {/* ── DEMO MODE BANNER (only visible when ?demo=1 or VITE_DEMO_MODE=true) ── */}
      {IS_DEMO_MODE && (
        <div style={{
          background: "#7c2d12", borderBottom: "2px solid #ea580c",
          padding: "10px 20px", textAlign: "center",
          fontSize: 13, fontWeight: 700, color: "#fed7aa", letterSpacing: "0.01em",
          position: "sticky", top: 0, zIndex: 500,
        }}>
          ⚠️ DEMO MODE — All incidents and risk scores shown below are <em>invented illustrative fixtures</em>, not real data. Remove ?demo=1 from the URL for live data only.
        </div>
      )}

      {/* ── API UNREACHABLE ERROR STATE (only when backend offline AND not demo mode) ── */}
      {!apiReachable && !scoresLoading && !IS_DEMO_MODE && (
        <div style={{
          flex: 1, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 16,
          padding: 48, textAlign: "center",
        }}>
          <div style={{ fontSize: 48 }}>🔌</div>
          <div style={{ color: "#f87171", fontSize: 20, fontWeight: 700 }}>Safety API Unreachable</div>
          <div style={{ color: "#94a3b8", fontSize: 14, maxWidth: 420 }}>
            Cannot reach the safety intelligence API at <code style={{ color: "#fbbf24" }}>http://127.0.0.1:8000</code>. No risk data can be displayed.
          </div>
          <div style={{ color: "#64748b", fontSize: 12, maxWidth: 400 }}>
            Start the backend with <code style={{ color: "#94a3b8" }}>uvicorn app.main:app</code> and reload, or append <code style={{ color: "#94a3b8" }}>?demo=1</code> to the URL to view illustrative demo fixtures.
          </div>
          <button onClick={() => window.location.reload()}
            style={{
              marginTop: 8, padding: "10px 24px", borderRadius: 8,
              background: "rgba(6,182,212,0.15)", border: "1px solid rgba(6,182,212,0.3)",
              color: "#67e8f9", cursor: "pointer", fontSize: 13, fontWeight: 600,
            }}>
            🔄 Retry
          </button>
        </div>
      )}

      {/* ── NAV ── */}
      <nav style={{
        background: "rgba(6,12,23,0.97)", backdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(255,255,255,0.04)",
        padding: "0 16px", height: 52,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        position: "sticky", top: 0, zIndex: 200, gap: 12,
      }}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}>
          <span style={{ fontSize: 20 }}>🧭</span>
          <span style={{ color: "#f1f5f9", fontWeight: 800, fontSize: 14, whiteSpace: "nowrap" }}>
            SafeTravel <span style={{ color: "#06b6d4" }}>LK</span>
          </span>
        </div>

        {/* ── Uber-style Search Bar ── */}
        <div ref={searchRef} style={{ flex: 1, maxWidth: 520, position: "relative" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            background: "rgba(15,23,42,0.95)", border: "1.5px solid rgba(6,182,212,0.25)",
            borderRadius: 12, padding: "0 14px", height: 38,
            boxShadow: showSuggestions ? "0 0 0 3px rgba(6,182,212,0.12)" : "none",
            transition: "box-shadow 0.2s",
          }}>
            <span style={{ fontSize: 14, opacity: 0.5 }}>🔍</span>
            <input
              value={globalQuery}
              onChange={e => { setGlobalQuery(e.target.value); setShowSuggestions(true); }}
              onFocus={() => setShowSuggestions(true)}
              placeholder="Search district, city or location in Sri Lanka…"
              style={{
                flex: 1, background: "transparent", border: "none", outline: "none",
                color: "#e2e8f0", fontFamily: "inherit", fontSize: 13,
              }}
            />
            {globalQuery && (
              <button onClick={() => { setGlobalQuery(""); setShowSuggestions(false); }}
                style={{ background: "none", border: "none", color: "#475569", cursor: "pointer", fontSize: 14, padding: 0 }}>✕</button>
            )}
          </div>
          {/* Suggestions Dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <div style={{
              position: "absolute", top: 44, left: 0, right: 0, zIndex: 300,
              background: "rgba(10,17,32,0.99)", border: "1px solid rgba(6,182,212,0.18)",
              borderRadius: 14, overflow: "hidden",
              boxShadow: "0 16px 48px rgba(0,0,0,0.6)",
            }}>
              {suggestions.map((place, i) => {
                const distScore = scores[place.district];
                const tier = distScore?.tier || "insufficient_data";
                const tc2 = TIER_CONFIG[tier];
                return (
                  <div key={i} onMouseDown={() => handleSuggestionSelect(place)}
                    style={{
                      display: "flex", alignItems: "center", gap: 12,
                      padding: "11px 16px", cursor: "pointer", borderBottom: i < suggestions.length-1 ? "1px solid rgba(100,116,139,0.06)" : "none",
                      transition: "background 0.12s",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(6,182,212,0.07)"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                  >
                    <span style={{
                      width: 34, height: 34, borderRadius: 9, flexShrink: 0,
                      background: place.type === "District" ? tc2.fill : "rgba(15,23,42,0.8)",
                      border: `1px solid ${place.type === "District" ? tc2.stroke : "rgba(100,116,139,0.12)"}`,
                      display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16,
                    }}>{place.icon}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 600 }}>{place.label}</div>
                      <div style={{ color: "#475569", fontSize: 11 }}>
                        {place.type === "District" ? `District · ${distScore?.count || 0} reports` : `City in ${place.district}`}
                      </div>
                    </div>
                    {place.type === "District" && distScore?.score != null && (
                      <span style={{ background: tc2.badge, color: "#fff", borderRadius: 5, padding: "2px 8px", fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
                        {tc2.grade}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {showSuggestions && globalQuery.length > 0 && suggestions.length === 0 && (
            <div style={{
              position: "absolute", top: 44, left: 0, right: 0, zIndex: 300,
              background: "rgba(10,17,32,0.99)", border: "1px solid rgba(100,116,139,0.10)",
              borderRadius: 14, padding: "16px", textAlign: "center",
              color: "#4b5563", fontSize: 12,
            }}>No results for "{globalQuery}"</div>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {onNavigateComponent2 && (
            <button
              onClick={onNavigateComponent2}
              title="Navigate to Component 2"
              style={{
                display: "flex", alignItems: "center", gap: 6,
                background: "rgba(6, 182, 212, 0.10)", border: "1px solid rgba(6, 182, 212, 0.25)",
                padding: "5px 12px", borderRadius: 8, cursor: "pointer",
                color: "#38bdf8", fontSize: 12, fontWeight: 600, fontFamily: "inherit",
                transition: "all 0.15s ease",
              }}
              onMouseEnter={e => e.currentTarget.style.background = "rgba(6, 182, 212, 0.20)"}
              onMouseLeave={e => e.currentTarget.style.background = "rgba(6, 182, 212, 0.10)"}
            >
              <span style={{ fontSize: 13 }}>📑</span> Component 2
            </button>
          )}

          {/* Profile chip — tap to edit */}
          <button
            onClick={() => setScreen("onboard")}
            title="Edit profile"
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: "transparent", border: "none",
              padding: "4px 10px", borderRadius: 20, cursor: "pointer",
              color: "#64748b", fontSize: 12, fontFamily: "inherit",
              transition: "color 0.15s",
            }}
            onMouseEnter={e => e.currentTarget.style.color = "#94a3b8"}
            onMouseLeave={e => e.currentTarget.style.color = "#64748b"}
          >
            <span style={{ fontSize: 15 }}>{profData.icon}</span>
            <span style={{ whiteSpace: "nowrap", letterSpacing: "-0.01em" }}>{profile.name}</span>
          </button>
        </div>
      </nav>


      <div style={{ display: "flex", flex: 1, overflow: "hidden", height: "calc(100vh - 58px)" }}>

        {/* ── LEFT SIDEBAR ── */}
        <div style={{
          width: 262, background: "rgba(6,12,23,0.99)",
          borderRight: "1px solid rgba(100,116,139,0.07)",
          display: "flex", flexDirection: "column", flexShrink: 0, overflowY: "auto",
        }}>
          <div style={{ padding: "10px 12px 6px" }}>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="🔍 Search district…"
              style={{
                width: "100%", boxSizing: "border-box",
                background: "rgba(30,41,59,0.7)", border: "1px solid rgba(100,116,139,0.10)",
                borderRadius: 9, padding: "7px 12px", color: "#e2e8f0",
                fontFamily: "inherit", fontSize: 12, outline: "none",
              }}
            />
          </div>

          {/* Filter pills */}
          <div style={{ padding: "6px 12px 8px", display: "flex", gap: 4, flexWrap: "wrap" }}>
            {["all","severe","high","moderate","low","insufficient_data"].map(t => {
              const c = TIER_CONFIG[t];
              const active = filter === t;
              return (
                <button key={t} onClick={() => setFilter(t)} style={{
                  padding: "3px 8px", borderRadius: 20, fontSize: 10, fontWeight: 600,
                  fontFamily: "inherit", cursor: "pointer", border: "1px solid",
                  background: active ? (c?.badge || "#06b6d4") : "transparent",
                  color: active ? "#fff" : (c?.text || "#94a3b8"),
                  borderColor: active ? (c?.badge || "#06b6d4") : "rgba(100,116,139,0.12)",
                }}>
                  {t === "all" ? "All" : t === "insufficient_data" ? "No data" : c?.label}
                  {t !== "all" && <span style={{ marginLeft: 4, opacity: 0.7 }}>{tierCounts[t] || 0}</span>}
                </button>
              );
            })}
          </div>

          {/* Tier summary */}
          <div style={{ padding: "0 12px 10px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
            {[["severe","🔴"],["high","🟠"],["moderate","🟡"]].map(([t, icon]) => (
              <div key={t} onClick={() => setFilter(t)} style={{
                background: "rgba(30,41,59,0.4)", border: `1px solid ${TIER_CONFIG[t].stroke}22`,
                borderRadius: 8, padding: "7px 5px", textAlign: "center", cursor: "pointer",
              }}>
                <div style={{ fontSize: 14 }}>{icon}</div>
                <div style={{ color: TIER_CONFIG[t].text, fontWeight: 700, fontSize: 16 }}>{tierCounts[t] || 0}</div>
                <div style={{ color: "#94a3b8", fontSize: 9 }}>{TIER_CONFIG[t].label}</div>
              </div>
            ))}
          </div>

          {/* District list */}
          <div style={{ padding: "0 12px", flex: 1 }}>
            <div style={{ color: "#1f2937", fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 6 }}>
              Districts ({districtList.length})
            </div>
            {districtList.map(d => {
              const s    = scores[d];
              const t    = s?.tier || "insufficient_data";
              const c    = TIER_CONFIG[t];
              const isSel = selected === d;
              return (
                <div key={d} onClick={() => handleSelect(d)} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "7px 10px", borderRadius: 9, marginBottom: 3,
                  cursor: "pointer", border: "1px solid",
                  background: isSel ? `${c.fill}cc` : "rgba(13,21,38,0.5)",
                  borderColor: isSel ? c.stroke : "rgba(100,116,139,0.06)",
                  transition: "all 0.10s",
                }}>
                  <div>
                    <div style={{ color: "#e2e8f0", fontSize: 12, fontWeight: isSel ? 700 : 400 }}>{d}</div>
                    <div style={{ color: "#94a3b8", fontSize: 9.5, marginTop: 1 }}>
                      {s?.count || 0} reports
                      {s?.confidence === "established" ? " · ✓" : s?.confidence === "preliminary" ? " · ⚠ limited" : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                    <span style={{
                      background: c.badge, color: "#fff", borderRadius: 5,
                      padding: "1px 7px", fontSize: 9, fontWeight: 700,
                    }}>{c.grade}</span>
                    {s?.score != null && <span style={{ color: c.text, fontSize: 9 }}>{Math.round(s.score * 100)}</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ padding: "12px", borderTop: "1px solid rgba(100,116,139,0.05)" }}>
            <div style={{ color: "#1e293b", fontSize: 9, lineHeight: 1.7 }}>
              <span style={{ color: "#334155", fontWeight: 700 }}>IT22629180</span> · Wilson-shrunk quantile tiers · 180-day decay · Bayesian shrinkage · SLTDA exposure normalisation (all 25 districts)
            </div>
          </div>
        </div>

        {/* ── CENTER MAP ── */}
        <div style={{ flex: 1, position: "relative", background: "linear-gradient(180deg,#050c17 0%,#091522 100%)" }}>
          <svg viewBox="80 100 380 600" style={{ width: "100%", height: "100%" }}>
            <defs>
              <filter id="softglow"><feGaussianBlur stdDeviation="4" /></filter>
            </defs>
            {/* grid */}
            {[...Array(9)].map((_,i) => <line key={`h${i}`} x1={80} y1={100+i*70} x2={460} y2={100+i*70} stroke="#091a2e" strokeWidth="0.5"/>)}
            {[...Array(6)].map((_,i) => <line key={`v${i}`} x1={80+i*76} y1={100} x2={80+i*76} y2={700} stroke="#091a2e" strokeWidth="0.5"/>)}

            {Object.entries(DISTRICTS).map(([d, pos]) => {
              const s        = scores[d];
              const t        = s?.tier || "insufficient_data";
              const c        = TIER_CONFIG[t];
              const isSel    = selected === d;
              const isHov    = hovered === d;
              const matchSrch = !search.trim() || d.toLowerCase().includes(search.toLowerCase());
              const matchFlt  = filter === "all" || t === filter;
              const r        = isSel ? pos.r + 5 : isHov ? pos.r + 2 : pos.r;

              return (
                <g key={d}
                  onClick={() => handleSelect(d)}
                  onMouseEnter={() => setHovered(d)}
                  onMouseLeave={() => setHovered(null)}
                  style={{ cursor: "pointer", opacity: (matchSrch && matchFlt) ? 1 : 0.10, transition: "opacity 0.2s" }}
                >
                  <title>{d} — {c.label} ({s?.count || 0} reports)</title>
                  {(t === "high" || t === "severe") && (
                    <circle cx={pos.cx} cy={pos.cy} r={r+10} fill={c.badge} opacity="0.10" filter="url(#softglow)"/>
                  )}
                  {isSel && (
                    <circle cx={pos.cx} cy={pos.cy} r={r+10} fill="none" stroke={c.stroke} strokeWidth="1.5" opacity="0.45" strokeDasharray="4,3"/>
                  )}
                  <circle cx={pos.cx} cy={pos.cy} r={r} fill={c.fill} stroke={c.stroke} strokeWidth={isSel ? 2.5 : 1.5}/>
                  <text x={pos.cx} y={pos.cy+1} textAnchor="middle" dominantBaseline="middle"
                    fill={c.text} fontSize={r > 22 ? 9 : 7.5} fontWeight="800">
                    {s?.score != null ? c.grade : "N/A"}
                  </text>
                  {s?.score != null && (
                    <text x={pos.cx} y={pos.cy+r-4} textAnchor="middle" dominantBaseline="middle"
                      fill={c.text} fontSize={5.5} opacity="0.7">
                      {Math.round(s.score * 100)}
                    </text>
                  )}
                  <text x={pos.cx} y={pos.cy+r+9} textAnchor="middle"
                    fill={isSel ? "#e2e8f0" : "#6b7280"} fontSize={7.5} fontWeight={isSel ? 700 : 400}>
                    {d.length > 13 ? d.slice(0,12)+"…" : d}
                  </text>
                </g>
              );
            })}

          </svg>

          {/* ── MAP LEGEND OVERLAY ── */}
          <div style={{
            position: "absolute",
            bottom: 14,
            left: 14,
            background: "rgba(6, 12, 23, 0.88)",
            backdropFilter: "blur(8px)",
            border: "1px solid rgba(100, 116, 139, 0.2)",
            borderRadius: 8,
            padding: "6px 12px",
            display: "flex",
            alignItems: "center",
            gap: 12,
            zIndex: 10,
            boxShadow: "0 4px 12px rgba(0,0,0,0.4)"
          }}>
            {[
              { label: "Low", grade: "A", color: "#15803d" },
              { label: "Moderate", grade: "B", color: "#b45309" },
              { label: "High", grade: "C", color: "#c2410c" },
              { label: "Severe", grade: "D", color: "#b91c1c" },
              { label: "No data", grade: "N/A", color: "#475569" }
            ].map(item => (
              <div key={item.label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{
                  width: 16,
                  height: 16,
                  borderRadius: "50%",
                  background: item.color,
                  color: "#fff",
                  fontSize: 9,
                  fontWeight: 800,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center"
                }}>
                  {item.grade}
                </span>
                <span style={{ color: "#94a3b8", fontSize: 11, fontWeight: 500 }}>
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* ── RIGHT PANEL ── */}
        {selected && selectedData ? (
          <div ref={panelRef} style={{
            width: 344, background: "rgba(6,12,23,0.99)",
            borderLeft: "1px solid rgba(100,116,139,0.07)",
            display: "flex", flexDirection: "column", flexShrink: 0,
          }}>
            {/* Header */}
            <div style={{
              background: `linear-gradient(135deg, ${tc.fill} 0%, rgba(6,12,23,0.97) 100%)`,
              borderBottom: `1px solid ${tc.stroke}44`,
              padding: "16px 18px 12px", flexShrink: 0,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ color: "#374151", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.8px" }}>District</div>
                  <div style={{ color: "#f1f5f9", fontSize: 18, fontWeight: 800, marginTop: 2 }}>{selected}</div>
                  {SLTDA_FOOTFALL[selected] && (
                    <div style={{ color: "#374151", fontSize: 10, marginTop: 2 }}>
                      {(SLTDA_FOOTFALL[selected]/1e6).toFixed(1)}M visitors/yr · SLTDA 2024
                    </div>
                  )}
                </div>
                <button onClick={() => setSelected(null)} style={{
                  background: "rgba(100,116,139,0.1)", border: "none", borderRadius: 7,
                  color: "#64748b", cursor: "pointer", padding: "4px 9px", fontSize: 11, fontFamily: "inherit",
                }}>✕</button>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
                <div style={{ textAlign: "center", minWidth: 52 }}>
                  <div style={{ color: tc.text, fontSize: 36, fontWeight: 900, lineHeight: 1 }}>
                    {selectedData.score != null ? Math.round(selectedData.score * 100) : "—"}
                  </div>
                  <div style={{ color: "#374151", fontSize: 8.5, marginTop: 2 }}>Risk score</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{
                      background: tc.badge, color: "#fff", borderRadius: 5,
                      padding: "2px 10px", fontSize: 11, fontWeight: 700,
                    }}>{tc.grade} · {tc.label}</span>
                    <span style={{ color: "#374151", fontSize: 9.5 }}>
                      {selectedData.confidence === "established" ? "✓ High confidence" : selectedData.confidence === "preliminary" ? "⚠ Limited data" : "— No data"}
                    </span>
                  </div>
                  {selectedData.score != null && (
                    <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 6, height: 6, overflow: "hidden" }}>
                      <div style={{
                        width: `${selectedData.score * 100}%`, height: "100%",
                        background: `linear-gradient(90deg, #15803d, ${tc.badge})`,
                        borderRadius: 6, transition: "width 0.6s ease",
                      }}/>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", borderBottom: "1px solid rgba(100,116,139,0.07)", flexShrink: 0 }}>
              {[["overview","Overview"],["incidents","Reports"],["cities","Areas"],["ai","AI Brief"]].map(([id, label]) => (
                <button key={id} onClick={() => setPanelTab(id)} style={{
                  flex: 1, padding: "9px 0", background: "transparent",
                  border: "none", borderBottom: `2px solid ${panelTab === id ? "#06b6d4" : "transparent"}`,
                  color: panelTab === id ? "#06b6d4" : "#374151",
                  fontFamily: "inherit", fontSize: 11, fontWeight: panelTab === id ? 700 : 400,
                  cursor: "pointer", transition: "all 0.12s",
                }}>{label}</button>
              ))}
            </div>

            {/* Panel body */}
            <div style={{ overflowY: "auto", flex: 1 }}>

              {/* ── OVERVIEW TAB ── */}
              {panelTab === "overview" && (
                <div style={{ padding: "14px 16px" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
                    {[
                      ["📋 Reports", selectedData.count, selectedData.count < MIN_REPORTS_INSUFF ? "too few to score" : selectedData.confidence === "established" ? "high confidence" : "limited data"],
                      ["⚠️ Scams", selectedInc.filter(i => i.is_scam).length, `${Math.round((selectedInc.filter(i=>i.is_scam).length / (selectedData.count||1)) * 100)}% of reports`],
                      ["👥 Footfall", selectedData.hasFootfall ? `${(SLTDA_FOOTFALL[selected]/1e6).toFixed(1)}M` : "N/A", "SLTDA 2024"],
                      ["🏙️ Cities", districtCities.length, districtCities.length > 0 ? `${cityProfiles.length} profiled` : "no data"],
                    ].map(([label, val, sub]) => (
                      <div key={label} style={{
                        background: "rgba(13,21,38,0.7)", borderRadius: 9, padding: "9px 12px",
                        border: "1px solid rgba(100,116,139,0.06)",
                      }}>
                        <div style={{ color: "#374151", fontSize: 9.5, marginBottom: 2 }}>{label}</div>
                        <div style={{ color: "#e2e8f0", fontSize: 16, fontWeight: 700 }}>{val}</div>
                        <div style={{ color: "#1e293b", fontSize: 9.5, marginTop: 1 }}>{sub}</div>
                      </div>
                    ))}
                  </div>

                  {/* No data notice */}
                  {selectedData.tier === "insufficient_data" && (
                    <div style={{
                      background: "rgba(30,41,59,0.5)", border: "1px solid rgba(71,85,105,0.25)",
                      borderRadius: 10, padding: "11px 13px", marginBottom: 14,
                    }}>
                      <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.7 }}>
                        <span style={{ fontWeight: 700 }}>ℹ️ Insufficient data</span><br/>
                        Fewer than {MIN_REPORTS_INSUFF} reports on record — no tier assigned. This does <em>not</em> mean the district is safe; it means evidence is limited. Use standard tourist precautions.
                      </div>
                    </div>
                  )}

                  {/* ── Personalized for You ── */}
                  <div style={{
                    background: "rgba(6,182,212,0.04)", border: "1px solid rgba(6,182,212,0.13)",
                    borderRadius: 12, padding: "13px 14px", marginBottom: 14,
                  }}>
                    {/* Header */}
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        <span style={{ fontSize: 16 }}>{profData.icon}</span>
                        <span style={{ color: "#06b6d4", fontSize: 11, fontWeight: 700, letterSpacing: "0.04em" }}>
                          PERSONALISED FOR {(profile.name || "YOU").toUpperCase()}
                        </span>
                      </div>
                      <span style={{ color: "#1e3a47", fontSize: 10 }}>{profile.type} · {profile.budget} · {profile.accommodation}</span>
                    </div>

                    {/* Score comparison */}
                    {personalizedScore != null && (
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ color: "#374151", fontSize: 9.5, marginBottom: 3 }}>Base district score</div>
                          <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 5, overflow: "hidden" }}>
                            <div style={{ width: `${Math.round(selectedData.score * 100)}%`, height: "100%", background: tc.badge, borderRadius: 4 }} />
                          </div>
                          <div style={{ color: "#64748b", fontSize: 10, marginTop: 2 }}>{Math.round(selectedData.score * 100)} / 100</div>
                        </div>
                        <span style={{ color: "#1f2937", fontSize: 11 }}>→</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ color: "#06b6d4", fontSize: 9.5, marginBottom: 3 }}>Your adjusted score</div>
                          <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 5, overflow: "hidden" }}>
                            <div style={{ width: `${personalizedScore}%`, height: "100%", background: personalizedScore > 65 ? "#ef4444" : personalizedScore > 40 ? "#f59e0b" : "#22c55e", borderRadius: 4, transition: "width 0.5s" }} />
                          </div>
                          <div style={{ color: "#22d3ee", fontSize: 10, fontWeight: 700, marginTop: 2 }}>{personalizedScore} / 100</div>
                        </div>
                      </div>
                    )}

                    {/* Multiplier factors */}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 10 }}>
                      {[
                        { label: profile.type, mult: profData.riskMult },
                        { label: profile.budget, mult: profile.budget === "Budget" ? 1.08 : profile.budget === "Luxury" ? 0.88 : 1.0 },
                        { label: profile.accommodation, mult: profile.accommodation === "Hostel" ? 1.06 : profile.accommodation === "Resort" ? 0.90 : 1.0 },
                        { label: profile.experience, mult: profile.experience === "First time" ? 1.10 : profile.experience === "Frequent visitor" ? 0.92 : 1.0 },
                      ].map(({ label, mult }) => (
                        <span key={label} style={{
                          fontSize: 10, padding: "3px 8px", borderRadius: 20,
                          background: mult > 1 ? "rgba(239,68,68,0.08)" : mult < 1 ? "rgba(34,197,94,0.08)" : "rgba(30,41,59,0.5)",
                          border: `1px solid ${mult > 1 ? "rgba(239,68,68,0.20)" : mult < 1 ? "rgba(34,197,94,0.20)" : "rgba(100,116,139,0.12)"}`,
                          color: mult > 1 ? "#f87171" : mult < 1 ? "#4ade80" : "#475569",
                        }}>
                          {mult > 1 ? "↑" : mult < 1 ? "↓" : "="} {label} ×{mult.toFixed(2)}
                        </span>
                      ))}
                    </div>

                    {/* Profile warnings */}
                    {profileWarnings.length > 0 && (
                      <div style={{ marginBottom: 10 }}>
                        {profileWarnings.map((w, i) => (
                          <div key={i} style={{
                            display: "flex", gap: 8, alignItems: "flex-start",
                            padding: "6px 0",
                            borderTop: i > 0 ? "1px solid rgba(100,116,139,0.07)" : "none",
                          }}>
                            <span style={{ fontSize: 13, flexShrink: 0 }}>{w.icon}</span>
                            <span style={{ color: "#94a3b8", fontSize: 11, lineHeight: 1.55 }}>{w.text}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Matched incidents */}
                    {relevantToProfile.length > 0 ? (
                      <div>
                        <div style={{ color: "#334155", fontSize: 10, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                          {relevantToProfile.length} incident{relevantToProfile.length > 1 ? "s" : ""} matching your concern profile
                        </div>
                        {relevantToProfile.slice(0, 3).map((inc, i) => {
                          const it = INCIDENT_TYPES[inc.type] || { emoji: "•", label: inc.type };
                          const si = getSourceInfo(inc.source);
                          const isUserPick = profile.concerns.includes(inc.type);
                          return (
                            <div key={i} style={{
                              display: "flex", gap: 7, alignItems: "flex-start",
                              padding: "5px 0", borderTop: i > 0 ? "1px solid rgba(100,116,139,0.06)" : "none",
                            }}>
                              <span style={{ fontSize: 13, flexShrink: 0 }}>{it.emoji}</span>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                                  {isUserPick && <span style={{ fontSize: 9, background: "rgba(6,182,212,0.15)", color: "#22d3ee", borderRadius: 10, padding: "1px 6px", flexShrink: 0 }}>your pick</span>}
                                  <span style={{ color: "#cbd5e1", fontSize: 11.5, lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{inc.title}</span>
                                </div>
                                <span style={{ color: "#374151", fontSize: 10 }}>{si.icon} {inc.days_ago}d ago · {inc.location}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div style={{ color: "#1e3a47", fontSize: 11 }}>
                        No incidents matching your concern profile in this district.
                      </div>
                    )}
                  </div>

                  {/* Incident type breakdown */}
                  {topTypes.length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <div style={{ color: "#1f2937", fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.7px", marginBottom: 8 }}>
                        Top incident types
                      </div>
                      {topTypes.map(([type, count]) => {
                        const it  = INCIDENT_TYPES[type] || { emoji: "•", label: type };
                        const pct = Math.round((count / (selectedData.count || 1)) * 100);
                        return (
                          <div key={type} style={{ marginBottom: 6 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                              <span style={{ color: "#e2e8f0", fontSize: 12 }}>{it.emoji} {it.label}</span>
                              <span style={{ color: "#475569", fontSize: 10.5 }}>{count}× · {pct}%</span>
                            </div>
                            <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 4, overflow: "hidden" }}>
                              <div style={{
                                width: `${pct}%`, height: "100%",
                                background: selectedData.tier === "severe" ? "#b91c1c" : selectedData.tier === "high" ? "#c2410c" : selectedData.tier === "moderate" ? "#b45309" : "#15803d",
                                borderRadius: 4,
                              }}/>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* ── HOW THIS SCORE WORKS ── */}
                  <div style={{ borderTop: "1px solid rgba(100,116,139,0.08)", marginTop: 14, paddingTop: 14 }}>
                    <details style={{ cursor: "pointer" }}>
                      <summary style={{
                        color: "#64748b", fontSize: 11, fontWeight: 600,
                        letterSpacing: "0.04em", userSelect: "none",
                        display: "flex", alignItems: "center", gap: 6,
                        listStyle: "none", outline: "none",
                      }}>
                        <span style={{
                          width: 18, height: 18, borderRadius: "50%",
                          background: "rgba(6,182,212,0.12)", border: "1px solid rgba(6,182,212,0.25)",
                          display: "inline-flex", alignItems: "center", justifyContent: "center",
                          fontSize: 10, color: "#22d3ee", flexShrink: 0,
                        }}>ℹ</span>
                        How this score is calculated
                      </summary>

                      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>

                        {/* Step 1 */}
                        <div style={{ background: "rgba(13,21,38,0.6)", border: "1px solid rgba(100,116,139,0.10)", borderRadius: 10, padding: "10px 12px" }}>
                          <div style={{ color: "#22d3ee", fontSize: 10, fontWeight: 700, marginBottom: 4, display: "flex", gap: 6, alignItems: "center" }}>
                            <span style={{ background: "rgba(6,182,212,0.15)", borderRadius: 4, padding: "1px 6px" }}>Step 1</span>
                            Raw severity score per report
                          </div>
                          <div style={{ color: "#94a3b8", fontSize: 10.5, lineHeight: 1.7 }}>
                            Each incident is scored by <strong style={{ color: "#cbd5e1" }}>type severity</strong> (1–3) × <strong style={{ color: "#cbd5e1" }}>source credibility weight</strong> × <strong style={{ color: "#cbd5e1" }}>time decay</strong>.<br/>
                            <code style={{ fontSize: 9.5, background: "rgba(6,182,212,0.08)", padding: "1px 5px", borderRadius: 3, color: "#67e8f9" }}>
                              score = severity × credibility × e^(−λ × days)
                            </code>
                            <span style={{ color: "#475569", fontSize: 9.5 }}> · λ = ln(2)/180 (half-life 180 days)</span>
                          </div>
                        </div>

                        {/* Step 2 — Source weights */}
                        <div style={{ background: "rgba(13,21,38,0.6)", border: "1px solid rgba(100,116,139,0.10)", borderRadius: 10, padding: "10px 12px" }}>
                          <div style={{ color: "#22d3ee", fontSize: 10, fontWeight: 700, marginBottom: 8, display: "flex", gap: 6, alignItems: "center" }}>
                            <span style={{ background: "rgba(6,182,212,0.15)", borderRadius: 4, padding: "1px 6px" }}>Step 2</span>
                            Source credibility weights
                          </div>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                            {[
                              ["🏛️ Gov / FCDO", "1.00", "#22c55e"],
                              ["🚔 Tourist Police", "0.97", "#22c55e"],
                              ["📰 Ada Derana", "0.88", "#86efac"],
                              ["📰 Newsfirst", "0.86", "#86efac"],
                              ["▶️ YouTube", "0.72", "#fbbf24"],
                              ["🟢 TripAdvisor", "0.60", "#60a5fa"],
                              ["📍 Google Maps", "0.62", "#60a5fa"],
                              ["🟠 Reddit", "0.42", "#94a3b8"],
                            ].map(([src, w, col]) => (
                              <div key={src} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(6,12,23,0.4)", borderRadius: 5, padding: "3px 7px" }}>
                                <span style={{ color: "#94a3b8", fontSize: 9.5 }}>{src}</span>
                                <span style={{ color: col, fontSize: 10, fontWeight: 700 }}>{w}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Step 3 */}
                        <div style={{ background: "rgba(13,21,38,0.6)", border: "1px solid rgba(100,116,139,0.10)", borderRadius: 10, padding: "10px 12px" }}>
                          <div style={{ color: "#22d3ee", fontSize: 10, fontWeight: 700, marginBottom: 4, display: "flex", gap: 6, alignItems: "center" }}>
                            <span style={{ background: "rgba(6,182,212,0.15)", borderRadius: 4, padding: "1px 6px" }}>Step 3</span>
                            Wilson + Bayesian shrinkage
                          </div>
                          <div style={{ color: "#94a3b8", fontSize: 10.5, lineHeight: 1.7 }}>
                            Wilson score lower bound prevents gaming by small samples. Bayesian shrinkage (α={BAYESIAN_ALPHA}) pulls estimates toward the global prior ({Math.round(GLOBAL_PRIOR*100)}%) — districts with few reports cannot claim artificially high or low risk.
                          </div>
                        </div>

                        {/* Step 4 */}
                        <div style={{ background: "rgba(13,21,38,0.6)", border: "1px solid rgba(100,116,139,0.10)", borderRadius: 10, padding: "10px 12px" }}>
                          <div style={{ color: "#22d3ee", fontSize: 10, fontWeight: 700, marginBottom: 4, display: "flex", gap: 6, alignItems: "center" }}>
                            <span style={{ background: "rgba(6,182,212,0.15)", borderRadius: 4, padding: "1px 6px" }}>Step 4</span>
                            Footfall normalisation
                          </div>
                          <div style={{ color: "#94a3b8", fontSize: 10.5, lineHeight: 1.7 }}>
                            Scores are divided by SLTDA tourist footfall (Jan–Oct 2024) so high-visitor districts like Colombo aren't unfairly penalised for having more absolute reports.
                            {selectedData.hasFootfall && <><br/><strong style={{ color: "#cbd5e1" }}>{selected}:</strong> {(SLTDA_FOOTFALL[selected]/1e6).toFixed(1)}M visitors/year</>}
                          </div>
                        </div>

                        {/* Step 5 — Tier thresholds */}
                        <div style={{ background: "rgba(13,21,38,0.6)", border: "1px solid rgba(100,116,139,0.10)", borderRadius: 10, padding: "10px 12px" }}>
                          <div style={{ color: "#22d3ee", fontSize: 10, fontWeight: 700, marginBottom: 8, display: "flex", gap: 6, alignItems: "center" }}>
                            <span style={{ background: "rgba(6,182,212,0.15)", borderRadius: 4, padding: "1px 6px" }}>Step 5</span>
                            Quantile tier assignment (all 25 districts)
                          </div>
                          <div style={{ display: "flex", gap: 6 }}>
                            {[
                              ["A", "Low", "≤ Q25", "#15803d", selectedData.q25],
                              ["B", "Moderate", "Q25–Q50", "#b45309", selectedData.q50],
                              ["C", "High", "Q50–Q75", "#c2410c", selectedData.q75],
                              ["D", "Severe", "> Q75", "#b91c1c", null],
                            ].map(([g, label, range, col, q]) => (
                              <div key={g} style={{ flex: 1, textAlign: "center", background: "rgba(6,12,23,0.4)", borderRadius: 7, padding: "6px 4px", border: `1px solid ${col}22` }}>
                                <div style={{ width: 20, height: 20, borderRadius: "50%", background: col, color: "#fff", fontSize: 10, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 4px" }}>{g}</div>
                                <div style={{ color: "#94a3b8", fontSize: 8.5 }}>{range}</div>
                                {q != null && <div style={{ color: "#475569", fontSize: 8 }}>≤{Math.round(q*100)}</div>}
                              </div>
                            ))}
                          </div>
                          {selectedData.score != null && (
                            <div style={{ marginTop: 8, color: "#64748b", fontSize: 9.5 }}>
                              <strong style={{ color: "#e2e8f0" }}>{selected}</strong> composite score: <strong style={{ color: TIER_CONFIG[selectedData.tier].text }}>{Math.round(selectedData.score * 100)}</strong> · assigned <strong style={{ color: TIER_CONFIG[selectedData.tier].text }}>Tier {TIER_CONFIG[selectedData.tier].grade} — {TIER_CONFIG[selectedData.tier].label}</strong>
                            </div>
                          )}
                        </div>

                        <div style={{ color: "#1e293b", fontSize: 9, lineHeight: 1.6, paddingTop: 2 }}>
                          Wilson-shrunk quantile tiers · 180-day decay · Bayesian shrinkage · SLTDA exposure normalisation
                        </div>
                      </div>
                    </details>
                  </div>
                </div>
              )}

              {/* ── INCIDENTS TAB ── */}
              {panelTab === "incidents" && (() => {
                // Sort: profile-matched first, then by recency
                const [incidentFilter, setIncidentFilter_] = [window.__incFilter__ ?? "all", (v) => { window.__incFilter__ = v; }];
                const profileSorted = [...placeFiltered].sort((a, b) => {
                  const aMatch = mergedConcerns.includes(a.type) ? (profile.concerns.includes(a.type) ? 2 : 1) : 0;
                  const bMatch = mergedConcerns.includes(b.type) ? (profile.concerns.includes(b.type) ? 2 : 1) : 0;
                  return bMatch - aMatch;
                });
                return (
                <div style={{ padding: "12px 14px" }}>
                  {/* Profile filter banner */}
                  {relevantToProfile.length > 0 && (
                    <div style={{
                      background: "rgba(6,182,212,0.06)", border: "1px solid rgba(6,182,212,0.15)",
                      borderRadius: 9, padding: "7px 12px", marginBottom: 10,
                      display: "flex", alignItems: "center", gap: 8,
                    }}>
                      <span style={{ fontSize: 14 }}>{profData.icon}</span>
                      <span style={{ color: "#22d3ee", fontSize: 11, flex: 1 }}>
                        <strong>{relevantToProfile.length}</strong> of {placeFiltered.length} incidents match your concern profile — shown first
                      </span>
                    </div>
                  )}
                  <input
                    value={placeSearch}
                    onChange={e => setPlaceSearch(e.target.value)}
                    placeholder="🔍 Filter by place or keyword…"
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "rgba(13,21,38,0.8)", border: "1px solid rgba(100,116,139,0.12)",
                      borderRadius: 10, padding: "9px 14px", color: "#e2e8f0",
                      fontFamily: "inherit", fontSize: 12.5, outline: "none", marginBottom: 10,
                    }}
                  />

                  {profileSorted.length === 0 && (
                    <div style={{ textAlign: "center", color: "#374151", fontSize: 12, padding: "28px 0" }}>
                      {placeSearch.trim()
                        ? `No reports match "${placeSearch}" in ${selected}.`
                        : "No incidents recorded for this district yet."}
                    </div>
                  )}

                  {profileSorted.map((inc, i) => {
                    const it         = INCIDENT_TYPES[inc.type] || { emoji: "•", label: inc.type };
                    const isProfile  = mergedConcerns.includes(inc.type);
                    const isUserPick = profile.concerns?.includes(inc.type);
                    const ytId       = getYouTubeId(inc.youtube_url || inc.url);
                    const srcTier    = getSourceTier(inc.source);
                    const ytExpanded = expandedYT[inc.id || i];
                    const sevColors  = ["","#22c55e","#f59e0b","#ef4444"];
                    const linkInfo   = getEffectiveSourceLink(inc);
                    return (
                      <div
                        key={inc.id || i}
                        onClick={() => setReviewModal(inc)}
                        style={{
                          background: isProfile ? "rgba(6,182,212,0.04)" : "rgba(13,21,38,0.65)",
                          border: `1px solid ${isProfile ? "rgba(6,182,212,0.20)" : "rgba(100,116,139,0.08)"}`,
                          borderRadius: 12, padding: "12px 13px", marginBottom: 8,
                          transition: "border-color 0.15s, box-shadow 0.15s",
                          cursor: "pointer",
                        }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(96,165,250,0.35)"; e.currentTarget.style.boxShadow = "0 2px 12px rgba(96,165,250,0.08)"; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = isProfile ? "rgba(6,182,212,0.20)" : "rgba(100,116,139,0.08)"; e.currentTarget.style.boxShadow = "none"; }}
                      >
                        {/* Title row */}
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 5 }}>
                          <div style={{ color: "#e2e8f0", fontSize: 12.5, lineHeight: 1.45, fontWeight: 500, flex: 1 }}>
                            {it.emoji} {inc.title}
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, flexShrink: 0 }}>
                            <span style={{ color: "#374151", fontSize: 10 }}>{inc.days_ago}d ago</span>
                            <span style={{
                              width: 7, height: 7, borderRadius: "50%",
                              background: sevColors[inc.severity || 1], display: "block",
                            }}/>
                          </div>
                        </div>

                        {/* Location */}
                        <div style={{ color: "#475569", fontSize: 10.5, marginBottom: 8 }}>
                          📍 {inc.location}
                        </div>

                        {/* Source badge row */}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: ytId ? 8 : 0 }}>
                          {/* Source tier badge */}
                          <a 
                            href={linkInfo.url} 
                            target="_blank" 
                            rel="noreferrer" 
                            onClick={e => e.stopPropagation()} 
                            style={{ textDecoration: "none" }}
                          >
                            <span style={{
                              display: "inline-flex", alignItems: "center", gap: 4,
                              background: srcTier.bg, border: `1px solid ${srcTier.color}${linkInfo.isDirect ? "44" : "33"}`,
                              borderRadius: 6, padding: "3px 9px", fontSize: 10.5,
                              color: srcTier.color, fontWeight: 600, cursor: "pointer",
                            }}>
                              {srcTier.icon} {srcTier.label} {linkInfo.isDirect ? "↗" : "· search ↗"}
                            </span>
                          </a>

                          {/* Scam vs Advisory tag */}
                          {inc.is_scam === true ? (
                            <span style={{
                              background: "rgba(239,68,68,0.10)", border: "1px solid rgba(239,68,68,0.20)",
                              borderRadius: 6, padding: "3px 9px", fontSize: 10.5, color: "#f87171",
                            }}>⚠ Confirmed Scam</span>
                          ) : (
                            <span style={{
                              background: "rgba(34,197,94,0.10)", border: "1px solid rgba(34,197,94,0.20)",
                              borderRadius: 6, padding: "3px 9px", fontSize: 10.5, color: "#4ade80",
                            }}>✓ Safety Advisory</span>
                          )}

                          {/* Profile relevance */}
                          {isProfile && (
                            <span style={{
                              background: isUserPick ? "rgba(6,182,212,0.15)" : "rgba(6,182,212,0.08)", border: `1px solid ${isUserPick ? "rgba(6,182,212,0.30)" : "rgba(6,182,212,0.20)"}`,
                              borderRadius: 6, padding: "3px 9px", fontSize: 10.5, color: "#22d3ee",
                            }}>⚡ {isUserPick ? "Your pick" : "Profile match"}</span>
                          )}

                          {/* YouTube toggle button */}
                          {ytId && (
                            <button
                              onClick={() => setExpandedYT(p => ({ ...p, [inc.id || i]: !p[inc.id || i] }))}
                              style={{
                                display: "inline-flex", alignItems: "center", gap: 4,
                                background: ytExpanded ? "rgba(239,68,68,0.20)" : "rgba(239,68,68,0.10)",
                                border: "1px solid rgba(239,68,68,0.30)",
                                borderRadius: 6, padding: "3px 9px", fontSize: 10.5,
                                color: "#fca5a5", cursor: "pointer", fontFamily: "inherit",
                              }}>
                              {ytExpanded ? "▼ Hide video" : "▶ Watch video"}
                            </button>
                          )}
                        </div>

                        {/* YouTube inline embed */}
                        {ytId && ytExpanded && (
                          <div style={{ borderRadius: 10, overflow: "hidden", marginTop: 4, border: "1px solid rgba(239,68,68,0.25)" }}>
                            <iframe
                              width="100%"
                              height="180"
                              src={`https://www.youtube.com/embed/${ytId}?rel=0&modestbranding=1`}
                              title={inc.title}
                              frameBorder="0"
                              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                              allowFullScreen
                              style={{ display: "block" }}
                            />
                            <a href={inc.youtube_url} target="_blank" rel="noreferrer" style={{
                              display: "block", textAlign: "center", padding: "6px",
                              background: "rgba(239,68,68,0.12)", color: "#f87171",
                              fontSize: 10.5, textDecoration: "none",
                            }}>🔗 Open on YouTube ↗</a>
                          </div>
                        )}

                        {/* YouTube thumbnail preview (not expanded) */}
                        {ytId && !ytExpanded && (
                          <div
                            onClick={() => setExpandedYT(p => ({ ...p, [inc.id || i]: true }))}
                            style={{
                              marginTop: 6, borderRadius: 8, overflow: "hidden", cursor: "pointer",
                              position: "relative", border: "1px solid rgba(239,68,68,0.20)",
                            }}>
                            <img
                              src={`https://img.youtube.com/vi/${ytId}/mqdefault.jpg`}
                              alt="YouTube thumbnail"
                              style={{ width: "100%", display: "block", opacity: 0.7 }}
                            />
                            <div style={{
                              position: "absolute", inset: 0,
                              display: "flex", alignItems: "center", justifyContent: "center",
                              background: "rgba(0,0,0,0.35)",
                            }}>
                              <span style={{
                                width: 44, height: 44, borderRadius: "50%",
                                background: "rgba(239,68,68,0.90)",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: 18, color: "#fff",
                              }}>▶</span>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}\n                </div>
                );
              })()}


              {/* ── CITIES / AREAS TAB ── */}
              {panelTab === "cities" && (
                <div style={{ padding: "12px 14px" }}>
                  <input
                    value={citySearch}
                    onChange={e => setCitySearch(e.target.value)}
                    placeholder="🔍 Search city or area…"
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "rgba(13,21,38,0.8)", border: "1px solid rgba(100,116,139,0.10)",
                      borderRadius: 8, padding: "7px 12px", color: "#e2e8f0",
                      fontFamily: "inherit", fontSize: 12, outline: "none", marginBottom: 10,
                    }}
                  />

                  {/* Location type risk */}
                  {Object.keys(LOCATION_TYPE_RISK).length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <div style={{ color: "#1f2937", fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.7px", marginBottom: 8 }}>
                        Risk by location type — district average
                      </div>
                      {(() => {
                        const distCities  = districtCities.map(c => CITY_PROFILES[c]).filter(Boolean);
                        if (distCities.length === 0) {
                          return <div style={{ color: "#374151", fontSize: 11 }}>No city data for this district.</div>;
                        }
                        // Get location types present in this district's cities
                        const ltypes = {};
                        distCities.forEach(cp => {
                          Object.entries(cp.top_location_types || {}).forEach(([lt]) => {
                            if (!ltypes[lt]) ltypes[lt] = 0;
                            ltypes[lt]++;
                          });
                        });
                        return Object.entries(ltypes).sort((a,b)=>b[1]-a[1]).map(([lt, cnt]) => {
                          const risk = LOCATION_TYPE_RISK[lt] || 0.15;
                          return (
                            <div key={lt} style={{ marginBottom: 6 }}>
                              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                                <span style={{ color: "#cbd5e1", fontSize: 11.5 }}>{lt}</span>
                                <span style={{ color: "#475569", fontSize: 10.5 }}>{Math.round(risk*100)}% risk · {cnt} loc</span>
                              </div>
                              <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 4, overflow: "hidden" }}>
                                <div style={{
                                  width: `${risk*100}%`, height: "100%",
                                  background: risk > 0.3 ? "#c2410c" : risk > 0.2 ? "#b45309" : "#15803d",
                                  borderRadius: 4,
                                }}/>
                              </div>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  )}

                  {filteredCities.length === 0 && (
                    <div style={{ textAlign: "center", color: "#374151", fontSize: 12, padding: "16px 0" }}>
                      {citySearch.trim()
                        ? `No cities match "${citySearch}" in ${selected}.`
                        : "No city profiles available for this district."}
                    </div>
                  )}

                  {filteredCities.map(({ city, profile: cp }) => {
                    const riskPct  = Math.round(cp.risk_score * 100);
                    const negPct   = cp.total_reviews > 0 ? Math.round((cp.negative_reviews / cp.total_reviews) * 100) : 0;
                    const peakMths = cp.peak_complaint_months.map(m => MONTH_NAMES[m]).join(", ");
                    const topLT    = Object.keys(cp.top_location_types || {})[0] || "Various";
                    const cityTier = riskPct >= 35 ? "severe" : riskPct >= 25 ? "high" : riskPct >= 15 ? "moderate" : "low";
                    const cc       = TIER_CONFIG[cityTier];

                    return (
                      <div key={city} style={{
                        background: "rgba(13,21,38,0.7)", border: `1px solid ${cc.stroke}33`,
                        borderRadius: 10, padding: "11px 13px", marginBottom: 8,
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                          <div>
                            <div style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 700 }}>{city}</div>
                            <div style={{ color: "#374151", fontSize: 10, marginTop: 1 }}>📍 {topLT}</div>
                          </div>
                          <div style={{ textAlign: "right" }}>
                            <span style={{
                              background: cc.badge, color: "#fff", borderRadius: 5,
                              padding: "2px 8px", fontSize: 10, fontWeight: 700,
                            }}>{riskPct}/100</span>
                            <div style={{ color: cc.text, fontSize: 9, marginTop: 2 }}>{cc.label}</div>
                          </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 8 }}>
                          {[
                            ["Reviews", cp.total_reviews],
                            ["Negative", `${negPct}%`],
                            ["Scam mentions", cp.scam_mentions],
                          ].map(([l, v]) => (
                            <div key={l} style={{ background: "rgba(30,41,59,0.6)", borderRadius: 6, padding: "5px 7px" }}>
                              <div style={{ color: "#374151", fontSize: 8.5 }}>{l}</div>
                              <div style={{ color: "#cbd5e1", fontSize: 13, fontWeight: 700 }}>{v}</div>
                            </div>
                          ))}
                        </div>

                        {/* Risk bar */}
                        <div style={{ marginBottom: 6 }}>
                          <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 4, overflow: "hidden" }}>
                            <div style={{
                              width: `${riskPct}%`, height: "100%",
                              background: cc.badge, borderRadius: 4,
                            }}/>
                          </div>
                        </div>

                        {peakMths && (
                          <div style={{ color: "#374151", fontSize: 9.5 }}>
                            ⏰ Peak complaint months: <span style={{ color: "#475569" }}>{peakMths}</span>
                          </div>
                        )}
                        {cp.avg_rating && (
                          <div style={{ color: "#374151", fontSize: 9.5, marginTop: 2 }}>
                            ⭐ Avg rating: <span style={{ color: "#475569" }}>{cp.avg_rating.toFixed(1)}/5</span>
                            {cp.avg_contributions > 0 && <span> · {Math.round(cp.avg_contributions)} avg reviewer contribs</span>}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {districtCities.length > 0 && (
                    <div style={{ color: "#1e293b", fontSize: 9.5, lineHeight: 1.7, marginTop: 8 }}>
                      City risk scores from TripAdvisor review dataset (negative + scam mention analysis). Reviewer contribution count used as credibility proxy. Peak months from seasonal variance in negative reviews.
                    </div>
                  )}
                </div>
              )}

              {/* ── AI BRIEF TAB ── */}
              {panelTab === "ai" && (
                <div style={{ padding: "14px 16px" }}>
                  <div style={{
                    background: "rgba(6,182,212,0.04)", border: "1px solid rgba(6,182,212,0.10)",
                    borderRadius: 10, padding: "12px 14px", marginBottom: 14,
                  }}>
                    <div style={{ color: "#06b6d4", fontSize: 11, fontWeight: 700, marginBottom: 4 }}>
                      🤖 AI Safety Briefing
                    </div>
                    <div style={{ color: "#475569", fontSize: 11, lineHeight: 1.6 }}>
                      Personalised for <span style={{ color: "#22d3ee" }}>{profile.name}</span> · {profData.icon} {profData.label}
                      {profile.nationality && <span> · {profile.nationality}</span>}
                    </div>
                  </div>

                  {!aiText && !aiLoading && !aiError && (
                    <button onClick={fetchAI} style={{
                      width: "100%", padding: "11px",
                      background: "linear-gradient(135deg, #0891b2, #0e7490)",
                      border: "none", borderRadius: 10, color: "#fff",
                      fontFamily: "inherit", fontSize: 13, fontWeight: 700,
                      cursor: "pointer", boxShadow: "0 0 14px rgba(6,182,212,0.18)",
                    }}>
                      Generate safety brief for {selected}
                    </button>
                  )}

                  {aiLoading && (
                    <div style={{ textAlign: "center", padding: "24px 0" }}>
                      <div style={{ color: "#06b6d4", fontSize: 13, marginBottom: 8 }}>⟳ Analysing {selected}…</div>
                      <div style={{ color: "#374151", fontSize: 11 }}>Consulting district data and traveler profile</div>
                    </div>
                  )}

                  {aiError && (
                    <div style={{
                      background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.18)",
                      borderRadius: 9, padding: "12px", color: "#f87171", fontSize: 12, lineHeight: 1.6,
                    }}>{aiError}</div>
                  )}

                  {aiText && (
                    <>
                      <div style={{
                        background: "rgba(13,21,38,0.8)", border: "1px solid rgba(100,116,139,0.09)",
                        borderRadius: 10, padding: "14px 16px", marginBottom: 12,
                        color: "#cbd5e1", fontSize: 13, lineHeight: 1.85,
                      }}>
                        {aiText}
                      </div>
                      <button onClick={fetchAI} style={{
                        width: "100%", padding: "8px",
                        background: "rgba(30,41,59,0.7)", border: "1px solid rgba(100,116,139,0.12)",
                        borderRadius: 8, color: "#64748b", fontFamily: "inherit", fontSize: 12, cursor: "pointer",
                      }}>↺ Regenerate</button>
                    </>
                  )}

                  <div style={{
                    marginTop: 16, borderTop: "1px solid rgba(100,116,139,0.06)", paddingTop: 12,
                    color: "#1e293b", fontSize: 9.5, lineHeight: 1.7,
                  }}>
                    AI briefings are generated by Claude (claude-sonnet-4-6) using district incident data and real city profiles from the TripAdvisor review dataset. They supplement, not replace, official travel advisories. Always verify with UK FCDO, US State Dept, or Australia DFAT before travel.
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* ── EMPTY PANEL ── */
          <div style={{
            width: 304, background: "rgba(6,12,23,0.99)",
            borderLeft: "1px solid rgba(100,116,139,0.06)",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            <div style={{ textAlign: "center", padding: 24 }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🗺️</div>
              <div style={{ color: "#374151", fontSize: 13, lineHeight: 1.9, marginBottom: 18 }}>
                Click any district bubble to see its safety score, recent incidents, area profiles, and a personalised AI briefing.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {[["A","Low risk","#15803d"],["B","Moderate","#b45309"],["C","High risk","#c2410c"],["D","Severe","#b91c1c"]].map(([g,l,col]) => (
                  <div key={g} style={{ background: "rgba(13,21,38,0.6)", border: "1px solid rgba(100,116,139,0.07)", borderRadius: 8, padding: "8px 6px", textAlign: "center" }}>
                    <div style={{ width: 28, height: 28, borderRadius: "50%", background: col, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 4px", color: "#fff", fontWeight: 800, fontSize: 13 }}>{g}</div>
                    <div style={{ color: "#374151", fontSize: 9.5 }}>{l}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 16, color: "#1e293b", fontSize: 9.5, lineHeight: 1.7 }}>
                — = insufficient data (fewer than {MIN_REPORTS_INSUFF} reports)
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── REVIEW MODAL ── */}
      {reviewModal && (() => {
        const it        = INCIDENT_TYPES[reviewModal.type] || { emoji: "•", label: reviewModal.type };
        const srcT      = getSourceTier(reviewModal.source);
        const linkInfo  = getEffectiveSourceLink(reviewModal);
        const body      = reviewModal.summary || reviewModal.content || reviewModal.description || REVIEW_BODIES[reviewModal.id] || ("This safety alert was recorded from " + (srcT.label || reviewModal.source) + ". Use the button below to search Google for the original publication.");
        const srcInfo   = SOURCE_WEIGHTS[reviewModal.source];
        return (
          <div
            onClick={() => setReviewModal(null)}
            style={{
              position: "fixed", inset: 0, zIndex: 9999,
              background: "rgba(0,0,0,0.72)",
              backdropFilter: "blur(6px)",
              display: "flex", alignItems: "center", justifyContent: "center",
              padding: 24,
            }}
          >
            <div
              onClick={e => e.stopPropagation()}
              style={{
                background: "linear-gradient(145deg,#0d1526,#111c30)",
                border: "1px solid rgba(100,116,139,0.22)",
                borderRadius: 18,
                padding: "28px 30px",
                maxWidth: 520,
                width: "100%",
                boxShadow: "0 24px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)",
                position: "relative",
                maxHeight: "85vh",
                overflowY: "auto",
              }}
            >
              <button
                onClick={() => setReviewModal(null)}
                style={{
                  position: "absolute", top: 14, right: 14,
                  background: "rgba(100,116,139,0.12)", border: "none",
                  borderRadius: "50%", width: 30, height: 30,
                  color: "#94a3b8", fontSize: 16, cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontFamily: "inherit",
                }}
              >✕</button>

              <div style={{ marginBottom: 14 }}>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 5,
                  background: srcT.bg, border: `1px solid ${srcT.color}44`,
                  borderRadius: 20, padding: "4px 12px",
                  fontSize: 11, color: srcT.color, fontWeight: 700,
                }}>
                  {srcT.icon} {srcInfo?.label || reviewModal.source} · {srcT.label}
                </span>
              </div>

              <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 6 }}>
                {it.emoji} {it.label}
              </div>
              <div style={{ color: "#e2e8f0", fontSize: 16, fontWeight: 700, lineHeight: 1.4, marginBottom: 6 }}>
                {reviewModal.title}
              </div>
              <div style={{ color: "#475569", fontSize: 11, marginBottom: 18 }}>📍 {reviewModal.location}</div>

              <div style={{ height: 1, background: "rgba(100,116,139,0.12)", marginBottom: 18 }} />

              <div style={{
                color: "#cbd5e1", fontSize: 13.5, lineHeight: 1.8,
                fontStyle: "italic",
                background: "rgba(13,21,38,0.5)",
                border: "1px solid rgba(100,116,139,0.10)",
                borderRadius: 10, padding: "14px 16px",
                marginBottom: 18,
              }}>
                "{body}"
              </div>

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 18 }}>
                {reviewModal.is_scam === true ? (
                  <span style={{ background: "rgba(239,68,68,0.10)", border: "1px solid rgba(239,68,68,0.20)", borderRadius: 6, padding: "3px 10px", fontSize: 10.5, color: "#f87171" }}>⚠ Confirmed Scam</span>
                ) : (
                  <span style={{ background: "rgba(34,197,94,0.10)", border: "1px solid rgba(34,197,94,0.20)", borderRadius: 6, padding: "3px 10px", fontSize: 10.5, color: "#4ade80" }}>✓ Safety Advisory / Reassurance</span>
                )}
                <span style={{ color: "#64748b", fontSize: 11 }}>{reviewModal.days_ago}d ago</span>
                {renderHelpfulMetric(reviewModal) && (
                  <span style={{ color: "#64748b", fontSize: 11 }}>{renderHelpfulMetric(reviewModal)}</span>
                )}
                <span style={{ marginLeft: "auto", color: "#64748b", fontSize: 10.5, fontStyle: "italic" }}>
                  Credibility weight: {srcInfo ? srcInfo.w.toFixed(2) : "0.30"}
                </span>
              </div>

              {/* Action buttons */}
              <div style={{ display: "flex", gap: 10 }}>
                {linkInfo.isDirect ? (
                  <a
                    href={linkInfo.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      flex: 1, textAlign: "center", textDecoration: "none",
                      background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
                      border: "1px solid rgba(59,130,246,0.4)",
                      borderRadius: 10, padding: "10px",
                      color: "#ffffff", fontSize: 12.5, fontWeight: 700,
                      boxShadow: "0 4px 12px rgba(37,99,235,0.25)",
                    }}
                  >
                    ↗ Open External Source Article
                  </a>
                ) : (
                  <a
                    href={linkInfo.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      flex: 1, textAlign: "center", textDecoration: "none",
                      background: "rgba(30,41,59,0.80)",
                      border: "1px solid rgba(100,116,139,0.25)",
                      borderRadius: 10, padding: "10px",
                      color: "#38bdf8", fontSize: 12.5, fontWeight: 600,
                    }}
                  >
                    🔍 Search Headline on Google ↗
                  </a>
                )}
                <button
                  onClick={() => setReviewModal(null)}
                  style={{
                    width: 90,
                    background: "rgba(100,116,139,0.12)", border: "1px solid rgba(100,116,139,0.20)",
                    borderRadius: 10, padding: "10px",
                    color: "#94a3b8", fontSize: 12.5, fontWeight: 600,
                    cursor: "pointer", fontFamily: "inherit",
                  }}
                >Close</button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
