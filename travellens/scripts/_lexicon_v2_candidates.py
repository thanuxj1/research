# Final lexicon additions (v2). Selection rule, fixed before testing:
# keep a pattern only if it adds no false positive on the human gold set (Part A)
# and gains more than it costs on the development half (R001-R250).
EXTRA = {
    "facilities": [r"\bstaff\b", r"\bemployees?\b", r"\battendants?\b", r"\breception(ist)?\b",
                   r"\bexhibit(s|ion|ions)?\b", r"\bdisplays?\b", r"\bplacards?\b",
                   r"\b(guided|factory|boat|jeep|safari|tea|walking) tours?\b", r"\btour (guide|of the)\b",
                   r"\bplay ?(area|ground|equipment)s?\b", r"\bair.?condition", r"\bresorts?\b", r"\bcamp ?sites?\b",
                   r"\bsitting areas?\b", r"\bplaces? to (sit|eat|rest|stay)\b",
                   r"\bwater ?sports\b", r"\bboat (ride|riding|trip|rides)\b", r"\bequipment\b"],
    "roads_access": [r"\bworth the (walk|effort|climb|hike|trek|trip)\b", r"\b(time and )?effort\b",
                     r"\baccess(ed|es)\b", r"\brailway stations?\b", r"\bclamber", r"\bfitness\b", r"\bbikes?\b",
                     r"\bhard work\b",
                     r"\b(walk|climb|route)\b.{0,20}\b(closed|blocked)\b|\b(closed|blocked)\b.{0,20}\b(route|path|road)\b"],
    "safety": [r"\blife ?guards?\b", r"\bno.?swim", r"\bseat ?belts?\b", r"\bsunscreen\b|\bsun ?burn",
               r"\bstared at\b", r"\b(sea|water|waves?) (is|was|are|were) (very )?(calm|rough)\b",
               r"\binsect.?repell|\bmosquito", r"\bshould avoid\b"],
    "crowd": [r"\bhordes?\b", r"\b(a )?lot of (people|tourists|visitors|foreigners)\b",
              r"\bfew (people|visitors|participants|tourists)\b", r"\bweekends?\b", r"\b(all )?to ourselves\b",
              r"\btucked away\b", r"\bforeigners coming\b", r"\bhighly tourist"],
    "cleanliness": [r"\b(crystal.?)?clear (water|waters|sea|blue)\b", r"\bwater is \w*\s?(and )?(mostly )?clear\b",
                    r"\bpure water\b", r"\bpristine\b"],
    "price_value": [r"\bnot good value\b", r"\bvalue\b", r"\btokens?\b",
                    r"\b\d[\d,]*\s?(rs|lkr|rupees)\b|\b(rs|lkr)\.?\s?\d", r"\bfree to\b"],
}
