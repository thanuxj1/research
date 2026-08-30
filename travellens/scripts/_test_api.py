"""Adds Kandy review 2 to the combined test."""
import urllib.request, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from travellens.aspects import tag_segment
from travellens.polarity import lexicon_polarity, safety_recall_rule, site_rule_is_not_a_complaint
from travellens.segment import split_into_segments

POLARITY_LABEL = {"N": "negative", "P": "positive", "X": "neutral"}

def post(text, dest="Test Place", dist="Kandy"):
    body = json.dumps({'text': text, 'destination': dest, 'district': dist}).encode()
    req = urllib.request.Request('http://localhost:8778/analyse', data=body,
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as r: return json.loads(r.read())

def lex_summary(text):
    summary = {}
    for piece in split_into_segments(text):
        if len(piece.split()) < 3: continue
        aspects = tag_segment(piece)
        if not aspects: continue
        lex_label, _ = lexicon_polarity(piece)
        label, _ = site_rule_is_not_a_complaint(piece, lex_label)
        if "safety" in aspects:
            label, _ = safety_recall_rule(piece, label, True, lex_label)
        for k in aspects:
            cur = summary.get(k)
            new = POLARITY_LABEL.get(label, "neutral")
            if cur is None: summary[k] = new
            elif cur != "negative" and new == "negative": summary[k] = "negative"
    return summary

PASS = FAIL = 0

CASES = [
    ("Polluted lake",             "Kandy lake is polluted and the area is dirty.",                       "cleanliness", "negative"),
    ("Litter everywhere",         "There is garbage everywhere and plastic all over the beach.",          "cleanliness", "negative"),
    ("Well maintained",           "The place is very clean and well maintained.",                         "cleanliness", "positive"),
    ("Polite request to clean",   "They need to clean the pond area and surroundings.",                  "cleanliness", "negative"),
    ("Site rule - not complaint", "It is prohibited to take polythene inside the park.",                 "cleanliness", "neutral"),
    ("Direct danger",             "not safe to swim, the current is dangerous.",                         "safety",      "negative"),
    ("Hedged warning [KEY FIX]",  "maybe a bit dangerous for small children.",                           "safety",      "negative"),
    ("Drowning risk",             "People have drowned here, be very careful.",                          "safety",      "negative"),
    ("Slippery rocks",            "The rocks are very slippery when wet.",                               "safety",      "negative"),
    ("Positive safety",           "The area is perfectly safe for families.",                            "safety",      "positive"),
    ("Warning in 5-star review",  "Amazing place, but the currents are dangerous near the rocks.",       "safety",      "negative"),
    ("Broken roads",              "The roads are broken and very hard to drive on.",                     "roads_access","negative"),
    ("Slow walk [KEY FIX]",       "A slow walk through the tea estate.",                                 "roads_access","positive"),
    ("Exhausting hike",           "The hike is exhausting and very difficult.",                          "roads_access","negative"),
    ("Smooth easy road",          "The road is smooth and easy to reach.",                               "roads_access","positive"),
    ("Distance fact",             "It is an 8 km walk to the viewpoint.",                                "roads_access","neutral"),
    ("Filthy toilets",            "The toilets were filthy and locked.",                                 "facilities",  "negative"),
    ("Good food stalls",          "There are nice food stalls and clean restrooms.",                     "facilities",  "positive"),
    ("No bins",                   "There are no bins anywhere, the place needs better facilities.",      "facilities",  "negative"),
    ("Expensive entrance",        "The entrance fee is very expensive for what you get.",                "price_value", "negative"),
    ("Foreigner price gap",       "Foreigners pay 10 times more than locals, which is unfair.",          "price_value", "negative"),
    ("Great value",               "Very cheap and affordable, great value for money.",                   "price_value", "positive"),
    ("Factual price",             "Entrance fee for one local is 150 LKR.",                              "price_value", "neutral"),
    ("Too crowded",               "The place was too crowded and very noisy.",                           "crowd",       "negative"),
    ("Quiet=positive [KEY FIX]",  "it is very quiet.",                                                  "crowd",       "positive"),
    ("Peaceful=positive [KEY FIX]","The place was uncrowded and peaceful.",                              "crowd",       "positive"),
    ("Tranquil=positive",         "Absolutely tranquil and serene, no crowds at all.",                   "crowd",       "positive"),
    ("Beautiful scenery",         "Beautiful scenery and amazing views.",                                "scenery",     "positive"),
    ("Wildlife sighting",         "We saw elephants and peacocks, absolutely breathtaking.",              "scenery",     "positive"),
    ("Waterfall stunning",        "The waterfall is stunning and the landscape is gorgeous.",             "scenery",     "positive"),
    ("Galle Fort: scenery+",      "Galle Fort is so beautiful but the toilets are filthy.",              "scenery",     "positive"),
    ("Galle Fort: facilities-",   "Galle Fort is so beautiful but the toilets are filthy.",              "facilities",  "negative"),
    ("Warning inside praise",     "Amazing place, but the water is very dangerous near the edges.",      "safety",      "negative"),
]

W = 30
print()
print(f"{'Test case':<{W}}  {'Expected':<10}  {'Before':^13}  {'After':^13}  Status")
print("-" * (W + 52))
sections = {
    "CLEANLINESS":    range(0,5), "SAFETY":range(5,11),
    "ROADS":          range(11,16), "FACILITIES":range(16,19),
    "PRICE":          range(19,23), "CROWDING":range(23,27),
    "SCENERY":        range(27,30), "MIXED":range(30,33),
}
rows = []
for label, text, aspect, expected in CASES:
    before = lex_summary(text).get(aspect)
    after  = post(text)['summary'].get(aspect)
    ok = (after == expected)
    rows.append((label, text, aspect, expected, before, after, ok))

for section, rng in sections.items():
    print(f"\n  -- {section} --")
    for i in rng:
        label,_,_,expected,before,after,ok = rows[i]
        if ok: PASS+=1
        else:  FAIL+=1
        b=(before or "no tag")[:11]; a=(after or "no tag")[:11]
        print(f"  {'OK' if ok else '!!'} {label:<{W}}  {expected:<10}  {b:^13}  {a:^13}  {'PASS' if ok else 'FAIL <---'}")

total=PASS+FAIL
print(f"\n{'='*(W+52)}")
print(f"  REGRESSION: {PASS}/{total}  {'ALL PASS' if FAIL==0 else str(FAIL)+' FAIL'}")
print(f"{'='*(W+52)}")

# ── BOTH KANDY REVIEWS ────────────────────────────────────────────────────
REVIEWS = {
    "Kandy Review 1 (long)": {
        "text": """Kandy is a beautiful city with an amazing atmosphere, and the views from the hills around the city are absolutely breathtaking. Kandy Lake is one of my favourite places because the scenery is peaceful, the water reflects the surrounding hills, and walking around the lake in the evening is really enjoyable. The Temple of the Tooth is also impressive and the cultural atmosphere makes the whole area feel special. However, the experience is not perfect. The roads around the lake can be extremely busy, especially during the day, and the traffic is noisy and sometimes difficult to navigate. Some pavements are narrow, uneven and poorly maintained, which makes walking uncomfortable. There are also areas where the lake and surrounding streets look dirty, with rubbish and unpleasant smells, although other parts are very clean and well maintained. The number of tuk-tuks and people approaching tourists can also become annoying. Some drivers are friendly and helpful, but others seem more interested in taking tourists to expensive shops or convincing them to buy unnecessary tours. I was particularly uncomfortable when a driver insisted that I visit a particular gem shop and claimed that I would get a special discount, but the prices seemed much higher than expected. The city can also become very crowded around the Temple of the Tooth, and finding a quiet place can be difficult. At night I would be more careful in busy areas because some streets are poorly lit and the combination of traffic, crowds and aggressive sellers can make the experience uncomfortable. On the positive side, there are plenty of restaurants, hotels, shops and places to visit, and the local food is excellent. The scenery is definitely one of Kandy's biggest strengths, especially around sunset. Overall, Kandy is culturally fascinating and visually beautiful, but the traffic, cleanliness problems, crowded streets, aggressive selling and poor pedestrian infrastructure can significantly reduce the quality of the experience.""",
        "expected": {"roads_access":"negative","facilities":"negative","cleanliness":"negative","safety":"negative","price_value":"negative","crowd":"negative","scenery":"positive"},
    },
    "Kandy Review 2 (new)": {
        "text": """I spent three days in Kandy and came away with very mixed feelings. The city itself is incredibly beautiful, and the mountains surrounding Kandy create some fantastic views, particularly early in the morning when the mist covers the hills. Kandy Lake is a lovely place to walk around, and when the area is quiet the scenery is genuinely peaceful. The Temple of the Tooth is impressive and the cultural experience is something I would not want to miss. Unfortunately, getting around the city was not always enjoyable. The roads were not exactly easy to navigate, and traffic around the lake became frustratingly slow during busy periods. Some roads and pavements were in poor condition, with uneven surfaces and sections that appeared to have received very little maintenance. This was especially inconvenient when walking with luggage. Cleanliness was also inconsistent. Some areas around the lake were spotless, while other sections had plastic bottles, food wrappers and rubbish lying near the water. I wouldn't describe the entire lake as dirty, but there were definitely places that could have been cleaner. The crowds were another problem. During peak hours, the area around the Temple of the Tooth became so crowded that it was difficult to move comfortably, although visiting early in the morning was much more pleasant. There are plenty of hotels, restaurants, shops and other facilities, so finding somewhere to eat or stay is not difficult. However, some tourist-oriented shops seemed overpriced, and I was not convinced that every special discount offered to tourists represented a genuine bargain. One tuk-tuk driver quoted me a price that seemed reasonable at first, but after the journey he asked for considerably more than we had agreed. Another driver was honest and helpful, so my experience with transportation was inconsistent rather than completely bad. I also noticed that some people were very persistent when approaching tourists about tours, gems and souvenirs. I never experienced a serious safety problem, but I did feel uncomfortable walking through a few poorly lit streets late at night, particularly when groups of strangers were nearby. During the daytime I felt perfectly safe. Overall, I would still recommend Kandy because the scenery, culture and attractions are excellent, but visitors should be prepared for traffic, uneven pavements, inconsistent cleanliness, crowds and occasional problems with tourist prices. Kandy is not a perfect destination, but its beautiful surroundings and cultural attractions make the inconvenience worthwhile.""",
        "expected": {"roads_access":"negative","facilities":"negative","cleanliness":"negative","safety":"negative","price_value":"negative","crowd":"negative","scenery":"positive"},
    },
}

for review_name, data in REVIEWS.items():
    res = post(data["text"], "Kandy", "Kandy")
    summary = res['summary']
    rpass = rfail = 0
    print(f"\n{'='*(W+52)}")
    print(f"  {review_name}")
    print(f"{'='*(W+52)}")
    print(f"  {'Aspect':<15}  {'Expected':<12}  {'Got':<12}  Status")
    print("  " + "-"*46)
    for asp, exp in data["expected"].items():
        got = summary.get(asp) or "no tag"
        ok = (got == exp)
        if ok: rpass+=1
        else:  rfail+=1
        mark = "OK" if ok else "!! <--- WRONG"
        print(f"  {mark} {asp:<15}  {exp:<12}  {got:<12}")
    print(f"\n  Result: {rpass}/{rpass+rfail}  {'ALL CORRECT' if rfail==0 else str(rfail)+' WRONG'}")

sys.exit(0 if FAIL==0 else 1)
