import random


def generate_route(interest, days, budget):
    int_lower = str(interest or "nature").strip().lower()
    days_val = int(days) if days else 2

    if days_val <= 2:
        if int_lower == "beach":
            routes = ["Colombo -> Galle -> Colombo", "Colombo -> Bentota -> Colombo"]
        elif int_lower == "nature":
            routes = ["Colombo -> Kandy -> Colombo", "Colombo -> Kitulgala -> Colombo"]
        elif int_lower in ("cultural", "culture", "history"):
            routes = ["Colombo -> Kandy -> Colombo", "Colombo -> Sigiriya -> Colombo"]
        elif int_lower in ("wildlife", "safari"):
            routes = ["Colombo -> Udawalawe -> Colombo", "Colombo -> Yala -> Colombo"]
        elif int_lower == "adventure":
            routes = ["Colombo -> Kitulgala -> Colombo"]
        else:
            routes = ["Colombo -> Kandy -> Colombo"]

    elif days_val <= 4:
        if int_lower == "beach":
            routes = ["Colombo -> Galle -> Mirissa -> Colombo", "Colombo -> Bentota -> Galle -> Colombo"]
        elif int_lower == "nature":
            routes = ["Colombo -> Kandy -> Ella -> Colombo", "Colombo -> Kandy -> Nuwara Eliya -> Ella -> Colombo"]
        elif int_lower in ("cultural", "culture", "history"):
            routes = ["Colombo -> Kandy -> Sigiriya -> Colombo", "Colombo -> Sigiriya -> Polonnaruwa -> Colombo"]
        elif int_lower in ("wildlife", "safari"):
            routes = ["Colombo -> Galle -> Yala -> Colombo", "Colombo -> Udawalawe -> Colombo"]
        elif int_lower == "adventure":
            routes = ["Colombo -> Kitulgala -> Ella -> Colombo"]
        else:
            routes = ["Colombo -> Kandy -> Galle -> Colombo"]

    else:  # days >= 5
        if int_lower == "beach":
            routes = ["Colombo -> Bentota -> Galle -> Mirissa -> Colombo", "Colombo -> Trincomalee -> Arugam Bay -> Colombo"]
        elif int_lower == "nature":
            routes = ["Colombo -> Kandy -> Nuwara Eliya -> Ella -> Colombo", "Colombo -> Kitulgala -> Ella -> Colombo"]
        elif int_lower in ("cultural", "culture", "history"):
            routes = ["Colombo -> Kandy -> Sigiriya -> Polonnaruwa -> Colombo"]
        elif int_lower in ("wildlife", "safari"):
            routes = ["Colombo -> Galle -> Yala -> Udawalawe -> Colombo"]
        elif int_lower == "adventure":
            routes = ["Colombo -> Kitulgala -> Ella -> Arugam Bay -> Colombo"]
        else:
            routes = ["Colombo -> Kandy -> Ella -> Galle -> Colombo"]

    return random.choice(routes)
