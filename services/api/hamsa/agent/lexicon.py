"""Multilingual lexicons for the rules tier of the cascade.

Native-script and romanized forms for Hindi, Marathi, Tamil, Telugu, Bengali and Kannada.
Matching is on substrings of the lower-cased, digit-normalised message."""

from __future__ import annotations

INTENT_KEYWORDS: dict[str, list[str]] = {
    "greet": [
        "hi", "hello", "hey", "namaste", "namaskar", "vanakkam", "hii", "helo",
        "नमस्ते", "नमस्कार", "வணக்கம்", "నమస్కారం", "নমস্কার", "ನಮಸ್ಕಾರ",
    ],
    "browse": [
        "menu", "catalog", "catalogue", "price list", "rate list", "what do you have", "what all", "items", "products",
        "kya milega", "kya kya", "kya hai", "dikhao", "list bhejo", "enna irukku", "enna iruku", "emi unnayi", "ki ache",
        "मेनू", "मेन्यू", "मेनु", "மெனு", "మెనూ", "মেনু", "क्या मिलेगा", "क्या क्या", "क्या है", "दिखाओ", "सूची", "काय आहे", "என்ன இருக்கு", "என்ன இருக்கிறது", "ఏమి ఉన్నాయి",
        "ఏం ఉన్నాయి", "কী আছে", "কি আছে", "ಏನಿದೆ",
    ],
    "price": [
        "price", "rate", "cost", "how much", "kitna", "kitne", "kitni", "daam", "bhav", "evlo", "evvalavu", "vilai",
        "entha", "dhara", "koto", "dam koto",
        "कितना", "कितने", "कितनी", "दाम", "भाव", "किती", "விலை", "எவ்வளவு", "எத்தனை", "ధర", "ఎంత", "দাম", "কত", "ಬೆಲೆ", "ಎಷ್ಟು",
    ],
    "order": [
        "want", "need", "send", "order", "add", "give", "buy", "deliver",
        "chahiye", "bhejo", "bhej do", "dena", "de do", "dedo", "dijiye", "lena", "venum", "vendum", "anuppu", "kudunga",
        "kavali", "pampandi", "lagbe", "pathan", "pathiye", "beku",
        "चाहिए", "भेजो", "भेजिए", "दीजिए", "देना", "दे दो", "पाहिजे", "हवे", "हवं", "पाठवा", "வேணும்", "வேண்டும்", "அனுப்பு",
        "கொடுங்க", "కావాలి", "పంపండి", "চাই", "লাগবে", "পাঠান", "ಬೇಕು",
    ],
    "cart": [
        "cart", "basket", "my order so far", "what did i order", "kya liya", "total kitna", "bill",
        "कार्ट", "टोकरी", "बिल", "பில்", "బిల్", "বিল",
    ],
    "checkout": [
        "checkout", "check out", "confirm", "place order", "place the order", "that's all", "thats all", "done", "finalise",
        "finalize", "bas itna", "bas", "ho gaya", "pakka", "final", "podhum", "pothum", "chalu", "eituku", "etuku",
        "बस", "पक्का", "कन्फर्म", "इतना ही", "उतना ही", "झाले", "போதும்", "உறுதி", "అంతే", "చాలు", "ব্যাস", "এটুকুই", "ಸಾಕು",
    ],
    "pay": [
        "pay", "payment", "upi", "gpay", "phonepe", "paytm", "qr", "scan",
        "भुगतान", "पेमेंट", "பணம்", "பேமெண்ட்", "పేమెంట్", "পেমেন্ট",
    ],
    "paid": [
        "paid", "payment done", "pay kar diya", "pay kiya", "paise bhej", "bhej diya", "payment ho gaya", "kattiten",
        "anupitten", "pay chesanu", "diyechi", "pathiyechi",
        "भुगतान कर दिया", "पेमेंट कर दिया", "पैसे भेज", "भेज दिया", "பணம் அனுப்பிட்டேன்", "கட்டிட்டேன்", "చెల్లించాను",
        "পেমেন্ট করেছি", "টাকা পাঠিয়েছি",
    ],
    "status": [
        "status", "where is my order", "when will", "track", "kab aayega", "kab aaega", "kab milega", "kahan hai mera",
        "eppo varum", "eppudu vastundi", "kobe asbe",
        "कब आएगा", "कब मिलेगा", "कहाँ है", "कधी येईल", "எப்போ வரும்", "எப்போது வரும்", "ఎప్పుడు వస్తుంది", "কখন আসবে", "কবে আসবে",
        "ಯಾವಾಗ ಬರುತ್ತೆ",
    ],
    "hours": [
        "timing", "timings", "open", "close", "closing", "hours", "kab khulta", "kab khulega", "kab band",
        "खुला", "खुलता", "बंद", "समय", "வேலை நேரம்", "திறந்து", "సమయం", "খোলা", "সময়",
    ],
    "location": [
        "address", "location", "where are you", "kahan ho", "shop kahan", "map",
        "पता", "कहाँ हो", "दुकान कहाँ", "पत्ता", "முகவரி", "எங்கே", "చిరునామా", "ఎక్కడ", "ঠিকানা", "কোথায়", "ವಿಳಾಸ",
    ],
    "human": [
        "human", "owner", "manager", "real person", "talk to someone", "call me", "baat karni", "baat karao", "malik",
        "मालिक", "मालक", "बात करनी", "बात कराओ", "इंसान", "உரிமையாளர்", "முதலாளி", "యజమాని", "মালিক",
    ],
    "cancel": [
        "cancel", "cancel karo", "nahi chahiye", "vendam", "venda", "vaddu", "lagbe na",
        "रद्द", "कैंसल", "नहीं चाहिए", "नको", "வேண்டாம்", "ரத்து", "వద్దు", "రద్దు", "বাতিল", "লাগবে না", "ಬೇಡ",
    ],
    "remove": ["remove", "hatao", "hata do", "nikalo", "minus", "हटाओ", "हटा दो", "நீக்கு", "తీసేయండి", "বাদ দিন"],
    "thanks": [
        "thanks", "thank you", "thx", "dhanyavad", "shukriya", "nandri", "dhanyavadalu", "dhonnobad",
        "धन्यवाद", "शुक्रिया", "நன்றி", "ధన్యవాదాలు", "ধন্যবাদ", "ಧನ್ಯವಾದ",
    ],
}

# Completed-action markers; with a "pay" keyword they turn a request into a payment claim.
PAST_MARKERS: list[str] = [
    "done", "did", "sent", "completed", "diya", "kiya", "kar diya", "kardiya", "ho gaya", "hogaya", "bhej diya",
    "pannitten", "panniten", "anupitten", "chesanu", "chesa", "korechi", "diyechi",
    "कर दिया", "किया", "दिया", "हो गया", "केले", "झाले", "பண்ணிட்டேன்", "செய்தேன்", "அனுப்பிட்டேன்", "చేశాను", "పంపాను",
    "করেছি", "দিয়েছি", "ಮಾಡಿದ್ದೇನೆ",
]

# English catalog word -> other-language forms, used to auto-expand item aliases.
GROCERY_SYNONYMS: dict[str, list[str]] = {
    "sugar": ["चीनी", "शक्कर", "cheeni", "chini", "shakkar", "साखर", "சர்க்கரை", "sakkarai", "చక్కెర", "চিনি", "ಸಕ್ಕರೆ"],
    "rice": ["चावल", "chawal", "chaval", "तांदूळ", "அரிசி", "arisi", "బియ్యం", "biyyam", "চাল", "chal", "ಅಕ್ಕಿ"],
    "milk": ["दूध", "doodh", "dudh", "பால்", "paal", "పాలు", "paalu", "দুধ", "ಹಾಲು"],
    "atta": ["आटा", "aata", "atta", "gehun", "गेहूं", "கோதுமை மாவு", "godhumai", "గోధుమ పిండి", "আটা", "ಗೋಧಿ ಹಿಟ್ಟು"],
    "flour": ["आटा", "aata", "मैदा", "maida", "மாவு", "పిండి", "ময়দা"],
    "oil": ["तेल", "tel", "எண்ணெய்", "ennai", "ennei", "నూనె", "nune", "তেল", "ಎಣ್ಣೆ"],
    "dal": ["दाल", "daal", "dal", "டால்", "பருப்பு", "paruppu", "పప్పు", "pappu", "ডাল", "ಬೇಳೆ"],
    "egg": ["अंडा", "अंडे", "anda", "ande", "முட்டை", "muttai", "గుడ్లు", "guddu", "ডিম", "dim", "ಮೊಟ್ಟೆ"],
    "eggs": ["अंडे", "ande", "முட்டை", "muttai", "గుడ్లు", "ডিম", "ಮೊಟ್ಟೆ"],
    "bread": ["ब्रेड", "pav", "पाव", "ரொட்டி", "பிரெட்", "బ్రెడ్", "পাউরুটি", "ಬ್ರೆಡ್"],
    "tea": ["चाय", "chai", "chaha", "चहा", "டீ", "தேநீர்", "tea", "టీ", "চা", "ಟೀ"],
    "coffee": ["कॉफी", "காபி", "kaapi", "కాఫీ", "কফি", "ಕಾಫಿ"],
    "salt": ["नमक", "namak", "मीठ", "உப்பு", "uppu", "ఉప్పు", "লবণ", "নুন", "nun", "ಉಪ್ಪು"],
    "onion": ["प्याज", "pyaz", "pyaaz", "kanda", "कांदा", "வெங்காயம்", "vengayam", "ఉల్లిపాయ", "ullipaya", "পেঁয়াজ", "ಈರುಳ್ಳಿ"],
    "tomato": ["टमाटर", "tamatar", "टोमॅटो", "தக்காளி", "thakkali", "టమాటా", "టమోటా", "টমেটো", "ಟೊಮೆಟೊ"],
    "potato": ["आलू", "aloo", "alu", "बटाटा", "batata", "உருளைக்கிழங்கு", "urulai", "బంగాళాదుంప", "আলু", "ಆಲೂಗಡ್ಡೆ"],
    "soap": ["साबुन", "sabun", "साबण", "சோப்பு", "soppu", "సబ్బు", "সাবান", "ಸಾಬೂನು"],
    "biscuit": ["बिस्कुट", "biskut", "பிஸ்கட்", "బిస్కెట్", "বিস্কুট", "ಬಿಸ್ಕತ್"],
    "water": ["पानी", "pani", "paani", "தண்ணீர்", "thanni", "నీళ్ళు", "నీరు", "জল", "pani", "ನೀರು"],
    "ghee": ["घी", "ghee", "तूप", "நெய்", "nei", "నెయ్యి", "ঘি", "ತುಪ್ಪ"],
    "curd": ["दही", "dahi", "தயிர்", "thayir", "పెరుగు", "perugu", "দই", "doi", "ಮೊಸರು"],
    "paneer": ["पनीर", "பனீர்", "పనీర్", "পনির"],
    "chicken": ["चिकन", "murga", "கோழி", "சிக்கன்", "కోడి", "చికెన్", "মুরগি", "ಕೋಳಿ"],
}

NUMBER_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "a": 1, "an": 1, "dozen": 12,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7, "aath": 8,
    "nau": 9, "das": 10, "darjan": 12,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "दर्जन": 12,
    "दोन": 2, "पाच": 5,
    "onnu": 1, "rendu": 2, "moonu": 3, "naalu": 4, "anju": 5,
    "ஒன்று": 1, "ஒரு": 1, "இரண்டு": 2, "ரெண்டு": 2, "மூன்று": 3, "மூணு": 3, "நான்கு": 4, "நாலு": 4, "ஐந்து": 5,
    "okati": 1, "moodu": 3,
    "ఒకటి": 1, "ఒక": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5,
    "dui": 2,
    "এক": 1, "একটা": 1, "দুই": 2, "দুটো": 2, "তিন": 3, "চার": 4, "পাঁচ": 5,
    "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3,
}

UNIT_WORDS = {
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "किलो": "kg", "கிலோ": "kg", "కిలో": "kg",
    "কেজি": "kg", "ಕೆಜಿ": "kg",
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g", "ग्राम": "g", "கிராம்": "g", "గ్రాము": "g", "গ্রাম": "g",
    "l": "l", "litre": "l", "liter": "l", "litres": "l", "ltr": "l", "लीटर": "l", "லிட்டர்": "l", "లీటర్": "l", "লিটার": "l",
    "ml": "ml",
    "packet": "pkt", "packets": "pkt", "pkt": "pkt", "pack": "pkt", "पैकेट": "pkt", "பாக்கெட்": "pkt", "ప్యాకెట్": "pkt",
    "প্যাকেট": "pkt",
    "pc": "pc", "pcs": "pc", "piece": "pc", "pieces": "pc",
}
