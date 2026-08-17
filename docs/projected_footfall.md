# Projected SLTDA Footfall — Supplementary Research Notes

> **These figures are NOT used in the SafeTravelLK scoring system.**
> They are exploratory projections for future research purposes only.
> Only the 8 officially published districts are used for exposure-normalised scoring.

## Background

The SLTDA statistical bulletin (Jan–Oct 2024) publishes telecom-inferred inbound
presence figures for 8 districts. The remaining 17 districts have no published figures.

These projections were derived by fitting a simple regression:

```
log(footfall) ~ log(area_km2) + log(lodging_capacity) + district_type_factor
```

where `district_type_factor` encodes: tourism hub (1.5×), mid-tier (1.0×), peripheral (0.7×).

**This is not a validated model.** It produces illustrative order-of-magnitude estimates only.

---

## Official Published Figures (used in system)

| District | Official Footfall (Jan–Oct 2024) | Source |
|---|---|---|
| Colombo | 4,193,342 | SLTDA Bulletin |
| Galle | 2,671,580 | SLTDA Bulletin |
| Gampaha | 2,100,780 | SLTDA Bulletin |
| Kandy | 1,722,666 | SLTDA Bulletin |
| Matale | 1,249,150 | SLTDA Bulletin |
| Kalutara | 1,181,326 | SLTDA Bulletin |
| Matara | 1,170,772 | SLTDA Bulletin |
| Badulla | 818,133 | SLTDA Bulletin |

## Projected Figures (NOT used — exploratory only)

| District | Projected Footfall | Uncertainty | Basis |
|---|---|---|---|
| Nuwara Eliya | ~752,000 | ±40% | Tea-trail hub; high lodge density |
| Anuradhapura | ~735,000 | ±45% | Heritage site; seasonal |
| Kurunegala | ~693,000 | ±50% | Transit district |
| Puttalam | ~642,000 | ±55% | Coastal + Wilpattu access |
| Hambantota | ~618,000 | ±45% | Yala + port development |
| Kegalle | ~507,000 | ±50% | Pinnawala day-trip |
| Jaffna | ~505,000 | ±40% | Growing post-war destination |
| Batticaloa | ~461,000 | ±55% | East coast seasonal |
| Ampara | ~459,000 | ±55% | Arugam Bay surf season |
| Polonnaruwa | ~411,000 | ±45% | Heritage site |
| Trincomalee | ~348,000 | ±45% | East coast seasonal |
| Monaragala | ~327,000 | ±60% | Interior; limited data |
| Ratnapura | ~293,000 | ±55% | Gem industry visitors |
| Vavuniya | ~125,000 | ±65% | Transit |
| Kilinochchi | ~80,000 | ±70% | Minimal tourism |
| Mannar | ~78,000 | ±70% | Minimal tourism |
| Mullaitivu | ~76,000 | ±70% | Minimal tourism |

## Recommended Next Step

Request SLTDA to publish district-level telecom presence data for all 25 districts, or
use an alternative proxy such as Google Popular Times index or accommodation booking density.

Until that data is available, the 17 un-covered districts should remain on density-only
scoring with the label: *"SLTDA footfall not published for this district — exposure
normalisation not applied."*
