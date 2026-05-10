# =============================================================
# SRI LANKAN FOOD AI — FastAPI BACKEND
# Endpoints: /search (FAISS semantic), /recommend (XGBoost)
# =============================================================

from __future__ import annotations

import os
import re
import pickle
import logging
from pathlib import Path
from typing import Optional, List

import numpy as np
import pandas as pd
import faiss
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import LabelEncoder
from rank_bm25 import BM25Okapi

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# PATHS  — adjust if files live elsewhere
# ------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent
DATA_PATH  = BASE_DIR / "sri_lankan_food_dataset.csv"
MODEL_PATH = BASE_DIR / "sri_lankan_food_model.pkl"

# ------------------------------------------------------------------
# FOOD DESCRIPTIONS (rich text for semantic search)
# ------------------------------------------------------------------
FOOD_DESCRIPTIONS: dict[str, str] = {
    "String Hoppers": "Soft steamed rice noodle nests (indi appa). Breakfast with curry and coconut sambol. Mild, light, vegetarian. Excellent for beginners and tourists. Low spice. Popular morning meal.",
    "Plain Hoppers": "Bowl-shaped crispy rice flour pancakes with soft centers (appa). Breakfast or dinner. Crispy edges, soft middle. Vegetarian, mild, low spice. Street food.",
    "Egg Hoppers": "Hopper pancake with a soft cooked egg in the middle. Mild and beginner-friendly. Popular breakfast. Low spice. Good for tourists who dislike heat.",
    "Pittu": "Steamed cylinders of rice flour and coconut served with curry or coconut milk gravy. Light vegetarian breakfast. Soft and mild. Low spice. Traditional morning food.",
    "Kiribath": "Traditional Sri Lankan milk rice cooked with coconut milk. Served during New Year, celebrations, and breakfast. Mild, creamy, vegetarian. Low spice festive food.",
    "Kadala (Chickpeas)": "Boiled or curried chickpeas. Healthy Sri Lankan breakfast and snack. Vegetarian protein-rich food. Medium spice. Nutritious street food.",
    "Boiled Manioc": "Soft boiled cassava root. Eaten with spicy sambol. Vegetarian, filling, traditional breakfast. Low spice on its own.",
    "Boiled Sweet Potatoes": "Simple traditional Sri Lankan breakfast made from boiled sweet potatoes. Vegetarian, mild, healthy. Low spice.",
    "Dosa": "Thin crispy fermented rice and lentil pancake. Popular in Sri Lankan Tamil cuisine. Vegetarian. Mild low spice. Good breakfast or snack.",
    "Pol Roti": "Flat coconut roti eaten with sambol, curry, or tea. Vegetarian, filling. Medium spice depending on accompaniment. Street food and tea-time snack.",
    "Kurakkan Roti": "Healthy finger millet flatbread. Earthy flavour, high nutrition. Vegetarian, low spice, wholesome.",
    "Egg Roti": "Pan-fried roti filled with egg and vegetables. Commonly sold in street shops. Medium spice. Street food.",
    "Vegetable Roti": "Stuffed triangular flatbread filled with spicy vegetables. Vegetarian street food. Medium to high spice. Popular snack.",
    "Paratha": "Layered buttery flatbread. Popular in Sri Lankan Muslim cuisine. Mild, vegetarian. Good with curry. Low spice.",
    "Puri": "Deep-fried puffed bread. Eaten with curry. Vegetarian, mild. Low spice.",
    "Idli": "Soft steamed rice cakes served with sambol or curry. Vegetarian, mild, low spice. South Indian-Sri Lankan breakfast.",
    "Naan": "Soft oven-baked flatbread served with curries. Vegetarian, mild, low spice. Good for beginners.",
    "Godamba Roti": "Thin stretchy flatbread used in kottu preparation. Mild on its own. Street food base ingredient.",
    "Chicken Roll": "Crispy breadcrumb-coated snack filled with chicken and potato. Short eat. Tea-time snack. Medium spice.",
    "Fish Roll": "Deep-fried snack roll filled with savoury fish mixture. Short eat. Tea-time snack. Medium spice.",
    "Egg Roll": "Sri Lankan fried snack with egg filling and crispy coating. Short eat. Tea-time snack. Medium spice.",
    "Samosa": "Triangular fried pastry filled with vegetables, meat, or potatoes. Short eat. Tea-time snack. Vegetarian option available. Medium spice. Street food.",
    "Bread": "Basic bakery bread eaten with tea or curry. Mild, vegetarian.",
    "Roast Pan": "Crusty Sri Lankan bakery bread with soft inside. Mild, vegetarian.",
    "Sandwiches": "Simple bread snack served with tea. Mild, vegetarian.",
    "Chicken Bun": "Soft bakery bun filled with savoury chicken filling. Short eat. Tea-time snack. Medium spice.",
    "Fish Bun (Malu Pan)": "Popular Sri Lankan fish-filled bakery bun shaped like a fish. Short eat. Tea-time snack. Medium spice.",
    "Sausage Bun": "Bakery bun baked with sausage filling. Short eat. Tea-time snack.",
    "Egg Bun": "Soft bun with egg filling. Bakery short eat. Tea-time snack. Mild.",
    "Seeni Sambol Bun": "Sweet and spicy onion sambol stuffed bakery bun. Short eat. Tea-time snack. Medium spice.",
    "Kimbula Bun": "Sweet crocodile-shaped bakery bun. Popular among children. Sweet, mild, vegetarian tea-time snack.",
    "Fish Patties": "Crispy pastry snack filled with spicy fish. Eaten with tea. Short eat. Tea-time snack. Medium spice.",
    "Chicken Patties": "Savoury baked pastry filled with seasoned chicken and vegetables. Short eat. Tea-time snack. Medium spice.",
    "Ulundhu Vadai": "Savoury crispy lentil doughnut snack. Eaten with tea. Vegetarian short eat. Tea-time snack. Medium spice.",
    "Parippu vada": "Crunchy lentil fritter. Sri Lankan street food and tea snack. Vegetarian. Medium spice.",
    "Kola Kenda": "Traditional herbal porridge made from leafy greens and rice. Healthy, vegetarian, very mild. Low spice. Detox food.",
    "Vegetable Soup": "Light vegetable broth. Starter or comfort food. Vegetarian, mild, low spice.",
    "Chicken Soup": "Warm chicken broth. Comfort food for cold weather. Mild, low spice, light.",
    "Pork Soup": "Rich soup made using pork and Sri Lankan spices. Medium spice.",
    "Beef Soup": "Savoury beef broth with spices and vegetables. Medium spice.",
    "Mutton Soup": "Hearty mutton soup with strong Sri Lankan spice flavours. High spice.",
    "Vegetable Noodles": "Stir-fried noodles with vegetables and sauces. Vegetarian, medium spice. Street food.",
    "Egg Noodles": "Sri Lankan fried noodles with egg and vegetables. Medium spice. Street food.",
    "Chicken Noodles": "Popular street-style stir-fried noodles with chicken. Medium spice. Street food.",
    "Mixed Seafood Noodles": "Spicy noodles with prawns, cuttlefish, and seafood. High spice. Seafood lovers dish.",
    "Lunumiris": "Extremely spicy onion and chili sambol. Condiment eaten with rice or roti. Very high spice. Not for spice-sensitive tourists.",
    "Seeni Sambol": "Sweet caramelised onion relish. Paired with bread and hoppers. Low spice, sweet, vegetarian condiment.",
    "Coconut Sambol": "Fresh coconut chili sambol. Accompanies many Sri Lankan meals. Medium spice. Vegetarian condiment.",
    "Kochchi Sambol": "Very spicy sambol made using kochchi chilies. High spice condiment.",
    "Dhal Curry": "Mild lentil curry eaten daily in Sri Lanka. Vegetarian, low spice, comfort food. Beginner friendly. Good for tourists who dislike spicy food.",
    "Ala Baduma (Stir-fried Potato)": "Spicy fried potato side dish with curry leaves and spices. Vegetarian, medium spice.",
    "Omelet": "Simple egg omelet eaten with bread or rice. Mild, low spice.",
    "Kiri Hodi": "Mild coconut milk gravy served with kiribath. Vegetarian, very mild, low spice. Good for beginners.",
    "Ala Hodi (Potato White Curry)": "Creamy coconut milk potato curry with mild spices. Vegetarian, low spice, beginner friendly. Good for tourists.",
    "Chicken Curry": "Traditional Sri Lankan chicken curry with aromatic spices. High spice. Signature dish.",
    "Devilled Chicken": "Sweet spicy stir-fried chicken. Popular restaurant dish. High spice.",
    "Butter Chicken Curry": "Creamy mildly spiced chicken curry. Low spice. Beginner friendly. Good for tourists who dislike spicy food.",
    "Egg Curry": "Hard boiled eggs in curry gravy. Medium spice.",
    "Fish Curry": "Traditional Sri Lankan fish curry rich in spices. High spice. Seafood.",
    "Fish White Curry": "Mild coconut milk fish curry. Low spice. Seafood. Beginner friendly. Good for tourists who dislike spicy food.",
    "Devilled Fish": "Spicy sweet fried fish. Restaurant seafood dish. High spice.",
    "Fish Ambul Thiyal (Sour Fish Curry)": "Famous sour black pepper fish curry from southern Sri Lanka. High spice. Seafood. Must-try traditional dish.",
    "Cuttlefish Curry": "Spicy cuttlefish curry with Sri Lankan spices. High spice. Seafood.",
    "Devilled Cuttlefish": "Restaurant-style spicy cuttlefish stir fry. High spice. Seafood.",
    "Black Pork Curry": "Rich dark pork curry with roasted spices. High spice.",
    "Devilled Pork": "Sweet spicy pork stir fry. High spice. Restaurant dish.",
    "Beef Curry": "Sri Lankan beef curry with strong spice flavour. High spice.",
    "Devilled Beef": "Spicy beef stir fry with onions and peppers. High spice.",
    "Mutton Curry": "Traditional mutton curry with deep spicy flavour. High spice.",
    "Hot Butter Cuttlefish": "Popular crispy seafood restaurant dish in spicy butter sauce. High spice. Seafood must-try.",
    "Prawn Curry": "Spicy coconut prawn curry. High spice. Seafood.",
    "Devilled Prawns": "Sweet spicy prawn stir fry. Seafood restaurant dish. High spice.",
    "Crab Curry": "Rich spicy Sri Lankan crab curry famous among tourists. High spice. Seafood. Must-try.",
    "Meatball Curry": "Spiced meatballs in curry gravy. Medium to high spice.",
    "Mushroom Curry": "Vegetarian mushroom curry with coconut milk. Medium spice. Vegetarian.",
    "Soya Meat Curry": "Vegetarian curry made from textured soy protein. Medium spice. Vegetarian protein.",
    "Devilled Soya Meat": "Spicy vegetarian soy stir fry. High spice. Vegetarian.",
    "Polos Curry": "Young jackfruit curry with meat-like texture. Medium spice. Vegetarian. Popular vegan dish.",
    "Cashew Nut Curry": "Creamy mild curry made using cashew nuts. Low spice. Vegetarian. Good for tourists.",
    "Kir Kos (Jackfruit Curry)": "Traditional jackfruit curry with coconut. Medium spice. Vegetarian.",
    "Pumpkin Curry": "Sweet mild pumpkin curry with coconut milk. Low spice. Vegetarian. Beginner friendly.",
    "Beetroot Curry": "Colourful sweet beetroot curry. Low spice. Vegetarian.",
    "Green Bean Curry": "Simple vegetable curry with green beans. Low spice. Vegetarian.",
    "Ambarella Curry": "Tangy fruit curry with sweet sour flavour. Medium spice. Vegetarian.",
    "Kesel Muwa Curry (Banana Blossom Curry)": "Traditional banana blossom curry. Earthy taste. Medium spice. Vegetarian.",
    "Nelum Ala Curry (Lotus Root Curry)": "Lotus root curry with crunchy texture. Medium spice. Vegetarian.",
    "Eggplant Curry": "Soft eggplant curry with spices. Medium spice. Vegetarian.",
    "Wambatu Moju (Eggplant Pickle)": "Sweet sour fried eggplant pickle served with rice. Medium spice. Vegetarian condiment.",
    "Gotukola Sambol (Pennywort Salad)": "Healthy herbal salad made from gotukola leaves. Low spice. Vegetarian. Nutritious.",
    "Mango Chutney": "Sweet spicy mango condiment served with rice and curry. Medium spice. Vegetarian.",
    "Chicken Cutlet": "Deep-fried breadcrumb snack with chicken and potato. Short eat. Tea-time snack. Medium spice.",
    "Fish Cutlet": "Popular Sri Lankan party snack with fish and potato. Short eat. Tea-time snack. Medium spice. Seafood.",
    "Vegetable Cutlet": "Vegetarian fried breadcrumb snack. Short eat. Tea-time snack. Vegetarian. Medium spice.",
    "Papadam": "Thin crispy lentil cracker served with rice and curry. Low spice. Vegetarian side dish.",
    "Malay Pickle": "Sweet spicy preserved fruit pickle. Condiment. Medium spice.",
    "Rice and Curry": "Traditional Sri Lankan meal: rice with multiple curries and side dishes. High spice. Full meal. Must-try for tourists.",
    "Yellow rice": "Fragrant yellow rice cooked with spices. Low spice. Festive food. Vegetarian.",
    "Rathu Kekulu Rice (Red Raw Rice)": "Nutritious traditional Sri Lankan red rice. Healthy, mild. Vegetarian.",
    "Lamprais (Lump Rice)": "Dutch Burgher-influenced rice meal baked in banana leaf. Medium spice. Unique heritage dish.",
    "Biryani": "Spiced rice layered with meat and aromatic herbs. Medium to high spice. Festive rice dish.",
    "Vegetable Fried Rice": "Chinese-style fried rice with vegetables. Low to medium spice. Vegetarian.",
    "Chicken Fried Rice": "Fried rice with chicken and vegetables. Medium spice.",
    "Egg Fried Rice": "Rice stir-fried with egg and sauces. Low to medium spice.",
    "Seafood Fried Rice": "Fried rice with prawns, cuttlefish, and seafood. Medium spice. Seafood dish.",
    "Mixed Fried Rice": "Large fried rice combining meat, egg, and seafood. Medium spice.",
    "Chopsuey Rice": "Rice with stir-fried vegetables and meat in sauce. Medium spice.",
    "Vegetable Kottu": "Chopped roti street food with vegetables. Vegetarian, medium spice. Famous Sri Lankan street food.",
    "Chicken Kottu": "Sri Lanka's most famous street food: chopped roti with chicken and spices. High spice. Must-try street food.",
    "Egg Kottu": "Kottu roti with egg and vegetables. Medium spice. Street food.",
    "Cheese Kottu": "Modern cheesy kottu. Medium spice. Street food.",
    "Dolphin Kottu": "Crunchy deep-fried kottu variation. Street food. Medium spice.",
    "Seafood Kottu": "Kottu with prawns and seafood. High spice. Seafood street food.",
    "String Hopper kottu": "Kottu made from string hoppers. Medium spice. Street food.",
    "Watalappan": "Traditional Sri Lankan Muslim coconut custard dessert with jaggery. Sweet, mild, vegetarian dessert. No spice.",
    "Curd and Treacle": "Buffalo curd served with sweet kithul treacle. Sweet, mild, no spice. Traditional Sri Lankan dessert.",
    "Biscuit Pudding": "Layered chilled dessert made from biscuits and chocolate. Sweet, mild dessert. No spice. Beginner friendly.",
    "Caramel Pudding": "Sweet caramel custard dessert. Mild. No spice.",
    "Kiri Toffee (Milk Toffee)": "Traditional Sri Lankan milk candy enjoyed with tea. Sweet, mild. No spice. Vegetarian.",
    "Pol Toffee (Coconut Toffee)": "Sweet chewy coconut candy. Vegetarian sweet. No spice.",
    "Thala Bola (Sesame Seed bolls)": "Traditional sesame seed sweet balls. Vegetarian. No spice.",
    "Thala Karali (Sesame Seed Rolls)": "Crunchy sesame sweet rolls. Vegetarian. No spice.",
    "Wali thalapa": "Traditional sweet made from millet and jaggery. Vegetarian. No spice.",
    "Lavariya": "Sweet string hopper dessert filled with coconut and jaggery. Vegetarian dessert. No spice.",
    "Helapa": "Traditional sweet wrapped in kenda leaves. Vegetarian. No spice. Mild.",
    "Aggala": "Sweet rice and coconut snack ball. Vegetarian. No spice.",
    "Aluwa": "Diamond-shaped sweet made with rice flour and cashew. Vegetarian dessert. No spice. Traditional New Year sweet.",
    "Athirasa": "Traditional deep-fried sweet made with rice flour and jaggery. Vegetarian. No spice. Festive.",
    "Kevum (Oil Cake)": "Popular Sri Lankan New Year oil cake dessert. Vegetarian sweet. No spice.",
    "Aasmi": "Crispy festive sweet decorated with sugar syrup. Vegetarian. No spice. Festive.",
    "Kokis": "Crunchy deep-fried festive snack from Dutch colonial times. Vegetarian. No spice. Tea-time.",
    "Dosi": "Traditional fruit preserve sweet. Vegetarian. No spice.",
    "Pani Walalu": "Honey-coated crispy sweet snack. Vegetarian. No spice.",
    "Kalu Dodol": "Dark sticky sweet made from coconut milk and jaggery. Vegetarian. No spice.",
    "Coconut Cake": "Sweet coconut-flavoured cake for tea time. Vegetarian. No spice. Mild.",
    "Butter Cake": "Soft buttery Sri Lankan tea-time cake. Vegetarian. Mild. No spice.",
    "Ribbon Cake": "Colourful layered Sri Lankan celebration cake. Vegetarian. Mild. No spice.",
    "Jaggery": "Traditional unrefined palm sugar used in Sri Lankan sweets. Sweet, vegetarian, no spice.",
    "Spicy Cashew": "Crunchy fried cashew snack. Served with drinks. High spice. Bar snack.",
    "Ceylon Coffee": "Sri Lankan coffee drink from locally grown beans. Mild beverage. Low spice. Hot drink.",
    "Iced Coffee": "Cold sweet coffee beverage. Refreshing drink. No spice.",
    "Ceylon Tea": "World-famous Sri Lankan black tea. Enjoyed with snacks and short eats. Mild. No spice. Signature beverage. Hot drink.",
    "Green Tea": "Light healthy tea beverage. No spice. Mild drink.",
    "Iced Tea": "Cold refreshing tea drink. Beverage. No spice.",
    "Milk Tea": "Sri Lankan milk tea enjoyed with buns, rolls, and cutlets. Mild. Beverage. No spice. Hot drink.",
    "Bubble Tea": "Sweet milk tea drink with chewy tapioca pearls. Sweet beverage. No spice. Cold drink.",
    "Masala chai": "Spiced tea drink influenced by Indian cuisine. Low spice. Warm beverage. Hot drink.",
    "Thambili (King Coconut)": "Fresh king coconut water sold on Sri Lankan streets. Natural, mild, refreshing drink. No spice. Street beverage. Healthy cold drink.",
    "Koththamalli": "Traditional herbal coriander drink for wellness and colds. Mild herbal beverage. No spice. Hot drink.",
    "Ginger Beer": "Sweet spicy ginger-flavoured carbonated drink. Low spice. Cold beverage.",
    "Mango Lassi": "Sweet mango yogurt drink. No spice. Refreshing cold beverage. Sweet fruit drink.",
    "Lemonade": "Refreshing lemon drink. Cold beverage. No spice. Sweet drink.",
    "Avocado Juice": "Creamy sweet avocado milkshake-style drink. No spice. Cold beverage. Sweet fruit drink.",
    "Falooda": "Colourful dessert drink with jelly and ice cream. Sweet cold beverage. No spice. Dessert drink.",
    "Hot Chocolate": "Warm chocolate milk beverage. No spice. Sweet hot drink.",
    "Soya Milk": "Plant-based soy beverage. Vegetarian, vegan. No spice. Healthy drink.",
}

# ------------------------------------------------------------------
# SYNONYM EXPANSION
# ------------------------------------------------------------------
SYNONYM_MAP = {
    r'\bnot spicy\b':     'mild low spice gentle not spicy',
    r'\bmild\b':          'mild low spice not spicy gentle',
    r'\bdislike spicy\b': 'mild low spice not spicy beginner',
    r'\blow spice\b':     'mild low spice not spicy gentle',
    r'\bspicy\b':         'spicy high spice hot chili',
    r'\bveg\b':           'vegetarian vegan plant-based',
    r'\bvegan\b':         'vegetarian vegan plant-based',
    r'\bbreakfast\b':     'breakfast morning meal',
    r'\blunch\b':         'lunch midday meal',
    r'\bdinner\b':        'dinner evening meal',
    r'\bstreet\b':        'street food kottu roti vada roll',
    r'\bsweet\b':         'sweet dessert cake pudding',
    r'\bdessert\b':       'dessert sweet pudding cake toffee',
    r'\bseafood\b':       'seafood fish prawn crab cuttlefish',
    r'\btea\b':           'tea time short eat snack bun roll patties cutlet',
    r'\btourist\b':       'tourist beginner mild safe gentle',
    r'\bcheap\b':         'budget cheap affordable low price',
    r'\btraditional\b':   'traditional authentic Sri Lankan heritage',
    r'\bhealthy\b':       'healthy nutritious herbal light',
    r'\bdrink\b':         'drink beverage juice tea coffee milk',
    r'\bbeverage\b':      'drink beverage juice tea coffee milk',
    r'\bjuice\b':         'drink beverage juice fruit cold',
    r'\bcold drink\b':    'cold beverage iced chilled drink',
}

SPICY_SCORE = {'None': 1.0, 'Low': 0.9, 'Unknown': 0.7, 'Medium': 0.5, 'High': 0.2, 'Very High': 0.1}
BEVERAGE_INTENT_KW = ['drink', 'beverage', 'juice', 'lassi', 'falooda', 'coffee', 'lemonade', 'beer', 'shake', 'milkshake', 'smoothie', 'soda']
MEAL_INTENT_KW = ['lunch', 'dinner', 'breakfast', 'meal', 'dish', 'food', 'eat', 'snack', 'curry', 'rice']

# ------------------------------------------------------------------
# PYDANTIC MODELS
# ------------------------------------------------------------------
class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

class RecommendRequest(BaseModel):
    category: Optional[str] = None
    is_veg: Optional[str] = None
    meal_time: Optional[str] = None
    spicy_level: Optional[str] = None
    price_range: Optional[str] = None
    top_k: int = 5

class FoodItem(BaseModel):
    name: str
    description: str
    category: str
    is_veg: str
    meal_time: str
    spicy_level: str
    price_range: str

# ------------------------------------------------------------------
# APP STARTUP
# ------------------------------------------------------------------
app = FastAPI(title="Sri Lankan Food AI", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
state: dict = {}

def tokenize(text: str) -> list[str]:
    return re.findall(r'\w+', text.lower())

def expand_query(query: str) -> str:
    expanded = query
    for pattern, replacement in SYNONYM_MAP.items():
        if re.search(pattern, query, re.IGNORECASE):
            expanded += ' ' + replacement
    return expanded

def build_search_text(row: pd.Series) -> str:
    spicy_map = {
        'Low': 'mild low spice not spicy gentle',
        'Medium': 'medium spice moderate',
        'High': 'high spice very spicy hot chili',
        'Very High': 'extremely spicy very hot fiery',
        'None': 'no spice mild sweet',
    }
    spicy_tag = spicy_map.get(str(row.get('spicy_level', '')), '')
    veg_tag = ('vegetarian vegan plant-based' if str(row.get('is_veg', '')).lower() in ['true', '1', 'yes'] else 'non-vegetarian meat fish')
    desc = FOOD_DESCRIPTIONS.get(str(row['name']), 'Traditional Sri Lankan food.')
    return (
        f"Sri Lankan food called {row['name']}. {desc} "
        f"Category: {row['category']}. {veg_tag}. "
        f"Meal time: {row['meal_time']}. Spice: {row['spicy_level']}. {spicy_tag}. "
        f"Price: {row['price_range']}. Traditional Sri Lankan cuisine popular among locals and tourists."
    )

@app.on_event("startup")
async def startup():
    log.info("Loading dataset…")
    df = pd.read_csv(DATA_PATH)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df = df.fillna("Unknown")
    df['description'] = df['name'].map(FOOD_DESCRIPTIONS).fillna("Traditional Sri Lankan food.")
    df['search_text'] = df.apply(build_search_text, axis=1)
    state['df'] = df

    log.info("Loading embedding model…")
    emb_model = SentenceTransformer('BAAI/bge-small-en-v1.5')
    state['emb_model'] = emb_model

    log.info("Building FAISS index…")
    raw = emb_model.encode(df['search_text'].tolist(), show_progress_bar=True, normalize_embeddings=True)
    embs = np.array(raw).astype('float32')
    dim = embs.shape[1]
    idx = faiss.IndexFlatIP(dim)
    idx.add(embs)
    state['faiss_index'] = idx

    log.info("Building BM25 index…")
    corpus = [tokenize(t) for t in df['search_text'].tolist()]
    state['bm25'] = BM25Okapi(corpus)

    log.info("Loading XGBoost model…")
    with open(MODEL_PATH, 'rb') as f:
        xgb_model = pickle.load(f)
    state['xgb_model'] = xgb_model

    # Build label encoders from data (feature_encoders.pkl has import issues)
    feat_cols = ['category', 'is_veg', 'meal_time', 'spicy_level', 'price_range']
    encoders: dict[str, LabelEncoder] = {}
    for col in feat_cols:
        le = LabelEncoder()
        le.fit(df[col].astype(str))
        encoders[col] = le

    # Target encoder: map class indices → food names
    target_le = LabelEncoder()
    target_le.fit(df['name'].astype(str))
    state['encoders'] = encoders
    state['target_le'] = target_le

    log.info("✅ All models loaded. Ready!")

# ------------------------------------------------------------------
# /search  — hybrid FAISS + BM25
# ------------------------------------------------------------------
@app.post("/search", response_model=List[FoodItem])
async def search(req: SearchRequest):
    df: pd.DataFrame = state['df']
    emb_model: SentenceTransformer = state['emb_model']
    faiss_index = state['faiss_index']
    bm25: BM25Okapi = state['bm25']

    query_lower = req.query.lower()
    expanded = expand_query(req.query)

    want_beverage = any(kw in query_lower for kw in BEVERAGE_INTENT_KW)
    want_meal     = any(kw in query_lower for kw in MEAL_INTENT_KW)
    want_dessert  = ('dessert' in query_lower or 'sweet' in query_lower) and not want_beverage

    q_emb = emb_model.encode([expanded], normalize_embeddings=True).astype('float32')
    sem_scores, sem_idx = faiss_index.search(q_emb, 40)
    sem_scores, sem_idx = sem_scores[0], sem_idx[0]

    bm25_raw  = np.array(bm25.get_scores(tokenize(expanded)))
    bm25_max  = bm25_raw.max()
    bm25_norm = bm25_raw / bm25_max if bm25_max > 0 else bm25_raw

    bm25_top40 = np.argsort(bm25_norm)[::-1][:40]
    candidates = list(set(sem_idx.tolist() + bm25_top40.tolist()))
    sem_map    = dict(zip(sem_idx.tolist(), sem_scores.tolist()))

    alpha = 0.65
    scored = []
    for i in candidates:
        fused = alpha * sem_map.get(i, 0.0) + (1 - alpha) * float(bm25_norm[i])
        row = df.iloc[i]
        cat = str(row.get('category', '')).lower()
        is_drink = cat == 'drinks'
        is_dessert = 'dessert' in cat

        if any(kw in query_lower for kw in ['not spicy','mild','dislike spicy','low spice','tourist','beginner','non spicy']):
            fused *= SPICY_SCORE.get(str(row.get('spicy_level','Unknown')), 0.5)
        if 'vegetarian' in query_lower or 'vegan' in query_lower:
            if str(row.get('is_veg','')).lower() not in ['true','1','yes']:
                fused *= 0.1
        if 'seafood' in query_lower:
            if not any(kw in str(row['name']).lower() for kw in ['fish','prawn','crab','cuttlefish','seafood']):
                fused *= 0.15
        if 'tea' in query_lower and not want_beverage:
            if not any(kw in str(row['name']).lower() for kw in ['vada','roll','bun','cutlet','cake','kokis','toffee','patties','samosa','roti','sandwich','biscuit','bread']):
                fused *= 0.3
        if 'street food' in query_lower:
            if not any(kw in str(row['name']).lower() for kw in ['kottu','vada','roll','roti','bun','samosa']):
                fused *= 0.3
        if want_dessert and not is_dessert:
            fused *= 0.2
        if 'breakfast' in query_lower:
            if 'breakfast' in str(row.get('meal_time','')).lower():
                fused *= 1.2
            if is_drink:
                fused *= 0.1
        if want_beverage:
            fused *= (2.0 if is_drink else 0.15)
        if want_meal and not want_beverage and is_drink:
            fused *= 0.1

        scored.append((fused, i))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [df.iloc[i] for _, i in scored[:req.top_k]]

    return [FoodItem(
        name=str(r['name']),
        description=FOOD_DESCRIPTIONS.get(str(r['name']), str(r.get('description',''))),
        category=str(r['category']),
        is_veg=str(r['is_veg']),
        meal_time=str(r['meal_time']),
        spicy_level=str(r['spicy_level']),
        price_range=str(r['price_range']),
    ) for r in top]

# ------------------------------------------------------------------
# /recommend  — XGBoost structured recommendation
# ------------------------------------------------------------------
@app.post("/recommend", response_model=List[FoodItem])
async def recommend(req: RecommendRequest):
    df: pd.DataFrame = state['df']
    model = state['xgb_model']
    encoders: dict[str, LabelEncoder] = state['encoders']
    target_le: LabelEncoder = state['target_le']

    feat_cols = ['category', 'is_veg', 'meal_time', 'spicy_level', 'price_range']
    pref = {
        'category':    req.category or 'Unknown',
        'is_veg':      req.is_veg or 'Unknown',
        'meal_time':   req.meal_time or 'Unknown',
        'spicy_level': req.spicy_level or 'Unknown',
        'price_range': req.price_range or 'Unknown',
    }

    # Score each food item by probability from XGBoost
    scored_rows = []
    for _, row in df.iterrows():
        features = {}
        for col in feat_cols:
            val = pref[col] if pref[col] not in ('Unknown', None, '') else str(row[col])
            le = encoders[col]
            try:
                features[col] = le.transform([val])[0]
            except ValueError:
                features[col] = le.transform([str(row[col])])[0]

        X = np.array([[features[c] for c in feat_cols]])
        try:
            proba = model.predict_proba(X)[0]
            score = float(proba.max())
        except Exception:
            score = 0.0

        # Soft filter by user preferences
        if pref['is_veg'] not in ('Unknown', '') and pref['is_veg'].lower() in ['true','yes','1']:
            if str(row.get('is_veg','')).lower() not in ['true','1','yes']:
                score *= 0.05
        if pref['spicy_level'] not in ('Unknown', ''):
            if str(row['spicy_level']) != pref['spicy_level']:
                score *= 0.6
        if pref['category'] not in ('Unknown', ''):
            if str(row['category']).lower() != pref['category'].lower():
                score *= 0.5
        if pref['meal_time'] not in ('Unknown', ''):
            if pref['meal_time'].lower() not in str(row.get('meal_time','')).lower():
                score *= 0.6

        scored_rows.append((score, row))

    scored_rows.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in scored_rows[:req.top_k]]

    return [FoodItem(
        name=str(r['name']),
        description=FOOD_DESCRIPTIONS.get(str(r['name']), str(r.get('description',''))),
        category=str(r['category']),
        is_veg=str(r['is_veg']),
        meal_time=str(r['meal_time']),
        spicy_level=str(r['spicy_level']),
        price_range=str(r['price_range']),
    ) for r in top]

# ------------------------------------------------------------------
# /options  — return available filter values for dropdowns
# ------------------------------------------------------------------
@app.get("/options")
async def options():
    df: pd.DataFrame = state['df']
    return {
        "categories":   sorted(df['category'].dropna().unique().tolist()),
        "meal_times":   sorted(df['meal_time'].dropna().unique().tolist()),
        "spicy_levels": ['None', 'Low', 'Medium', 'High', 'Very High'],
        "price_ranges": sorted(df['price_range'].dropna().unique().tolist()),
        "veg_options":  [("Vegetarian", "True"), ("Non-Vegetarian", "False")],
    }

@app.get("/health")
async def health():
    return {"status": "ok", "models_loaded": bool(state)}


# ------------------------------------------------------------------
# HEALTH WARNING RULES
# Each condition maps to a list of rules. A rule fires when the
# food name or category matches any keyword in the rule.
# ------------------------------------------------------------------
HEALTH_RULES: dict[str, list[dict]] = {
    "diabetes": [
        {"keywords": ["toffee","cake","pudding","jaggery","treacle","falooda","bubble tea","lassi","ginger beer","lemonade","watalappan","aggala","aluwa","athirasa","kevum","aasmi","kokis","dosi","pani walalu","kalu dodol","ribbon cake","butter cake","coconut cake","lavariya","helapa","wali thalapa","thala","biscuit pudding","caramel pudding","curd and treacle","kiri toffee","pol toffee","seeni sambol bun","kimbula bun"], "severity": "danger",  "message": "High sugar content — avoid if diabetic"},
        {"keywords": ["rice","biryani","fried rice","hoppers","pittu","string hoppers","idli"], "severity": "caution", "message": "High glycaemic index — consume in small portions"},
        {"keywords": ["mango lassi","avocado juice","hot chocolate","soya milk","iced coffee","iced tea"], "severity": "caution", "message": "May contain added sugar — check before ordering"},
    ],
    "hypertension": [
        {"keywords": ["devilled","pickle","lunumiris","kochchi sambol","spicy cashew","papadam","malay pickle"], "severity": "danger",  "message": "High sodium / very spicy — may raise blood pressure"},
        {"keywords": ["mutton","beef","pork","black pork","meatball"], "severity": "caution", "message": "High saturated fat — limit for hypertension"},
        {"spice_levels": ["High","Very High"],                          "severity": "caution", "message": "Very spicy — may aggravate hypertension"},
    ],
    "coconut_allergy": [
        {"keywords": ["coconut","pol roti","hopper","pittu","kiribath","kiri hodi","watalappan","pol toffee","kalu dodol","coconut cake","coconut sambol","lavariya","helapa","aggala","aluwa","kevum","thala","string hoppers","dosa","idli","kola kenda","cashew nut curry","pumpkin curry","fish white curry","ala hodi","butter chicken","dhal curry","mushroom curry","polos"], "severity": "danger", "message": "Contains coconut — do not eat if allergic"},
    ],
    "seafood_allergy": [
        {"keywords": ["fish","prawn","crab","cuttlefish","seafood","malu"], "severity": "danger", "message": "Contains seafood — do not eat if allergic"},
    ],
    "nut_allergy": [
        {"keywords": ["cashew","spicy cashew","groundnut","peanut"], "severity": "danger", "message": "Contains nuts — do not eat if allergic"},
    ],
    "gluten_intolerance": [
        {"keywords": ["bread","roti","naan","paratha","puri","godamba","kottu","roll","bun","patties","cutlet","samosa","dosa","idli","sandwich","roast pan"], "severity": "danger",  "message": "Contains gluten (wheat) — avoid if coeliac or gluten intolerant"},
        {"keywords": ["string hoppers","pittu","hoppers","kiribath"],                                                                                           "severity": "caution", "message": "Rice-based but check preparation — cross-contamination risk"},
    ],
    "lactose_intolerance": [
        {"keywords": ["milk tea","hot chocolate","butter cake","kiri toffee","kiribath","kiri hodi","butter chicken","milk"], "severity": "danger",  "message": "Contains dairy / lactose — avoid if lactose intolerant"},
        {"keywords": ["cake","pudding","biscuit pudding","caramel pudding","curd"],                                           "severity": "caution", "message": "May contain dairy — check before ordering"},
    ],
    "high_cholesterol": [
        {"keywords": ["devilled","roll","cutlet","patties","samosa","oil cake","kevum","kokis","fried","bun","puri","deep"], "severity": "danger",  "message": "Deep fried / high fat — avoid with high cholesterol"},
        {"keywords": ["pork","beef","mutton","black pork","meatball"],                                                       "severity": "caution", "message": "High saturated fat — limit with high cholesterol"},
    ],
    "egg_allergy": [
        {"keywords": ["egg","omelet","omelette"], "severity": "danger", "message": "Contains egg — do not eat if allergic"},
    ],
    "kidney_disease": [
        {"keywords": ["mutton","beef","pork","chicken","prawn","crab","cuttlefish","fish","meatball","soya meat"], "severity": "caution", "message": "High protein — limit portions for kidney disease"},
        {"keywords": ["banana blossom","lotus root","ambarella","cashew nut","dhal"],                             "severity": "caution", "message": "High potassium — check with your doctor"},
        {"keywords": ["lunumiris","kochchi","devilled","pickle","papadam","spicy cashew"],                        "severity": "danger",  "message": "High sodium — harmful for kidney disease"},
    ],
    "gout": [
        {"keywords": ["mutton","beef","pork","black pork","meatball","anchovies","sardine","seafood","prawn","crab","cuttlefish","fish"], "severity": "danger",  "message": "High purine — triggers gout flare-ups"},
        {"keywords": ["beer","ginger beer","alcohol"],                                                                                   "severity": "danger",  "message": "Alcohol — worsens gout"},
        {"keywords": ["dhal","lentil","kadala","chickpea"],                                                                              "severity": "caution", "message": "Moderate purine — limit with gout"},
    ],
}


class HealthCheckRequest(BaseModel):
    foods: List[str]
    conditions: List[str]


class FoodWarning(BaseModel):
    food_name: str
    warnings: List[dict]  # [{condition, severity, message}]


@app.post("/health-check", response_model=List[FoodWarning])
async def health_check(req: HealthCheckRequest):
    """
    Given a list of food names and health conditions,
    return warnings for each food that conflicts with the conditions.
    """
    df: pd.DataFrame = state['df']
    results = []

    for food_name in req.foods:
        warnings = []
        food_lower = food_name.lower()

        # Find spicy_level from dataset
        match = df[df['name'].str.lower() == food_lower]
        spice_level = match.iloc[0]['spicy_level'] if len(match) > 0 else 'Unknown'

        for condition in req.conditions:
            rules = HEALTH_RULES.get(condition, [])
            for rule in rules:
                fired = False
                # keyword match
                if 'keywords' in rule:
                    if any(kw in food_lower for kw in rule['keywords']):
                        fired = True
                # spice level match
                if 'spice_levels' in rule:
                    if spice_level in rule['spice_levels']:
                        fired = True
                if fired:
                    warnings.append({
                        "condition": condition,
                        "severity":  rule['severity'],
                        "message":   rule['message'],
                    })

        if warnings:
            results.append(FoodWarning(food_name=food_name, warnings=warnings))

    return results