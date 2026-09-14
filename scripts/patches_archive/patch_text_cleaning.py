import re
import os

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")

with open(tc_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add normalize_political_parties
normalize_func = """
def normalize_political_parties(text):
    PARTY_MAP = {
        r'(?i)\\bதி\\.?மு\\.?க\\b': 'DMK',
        r'(?i)\\bஅ\\.?தி\\.?மு\\.?க\\b': 'AIADMK',
        r'(?i)\\bபா\\.?ஜ\\.?க\\b': 'BJP',
        r'(?i)\\bகாங்கிரஸ்\\b': 'Congress',
        r'(?i)\\bத\\.?வெ\\.?க\\b': 'TVK',
        r'(?i)\\bபா\\.?ம\\.?க\\b': 'PMK',
        r'(?i)\\bதே\\.?மு\\.?தி\\.?க\\b': 'DMDK',
        r'(?i)\\bநா\\.?த\\.?க\\b': 'NTK',
        r'(?i)\\bவி\\.?சி\\.?க\\b': 'VCK',
        r'(?i)\\bம\\.?தி\\.?மு\\.?க\\b': 'MDMK',
        r'(?i)\\bசி\\.?பி\\.?ஐ\\b': 'CPI',
        r'(?i)\\bசி\\.?பி\\.?எம்\\b': 'CPM',
        r'(?i)திராவிட\\s*முன்னேற்றக்\\s*கழகம்': 'DMK',
        r'(?i)அண்ணா\\s*திராவிட\\s*முன்னேற்றக்\\s*கழகம்': 'AIADMK',
        r'(?i)தமிழக\\s*வெற்றிக்\\s*கழகம்': 'TVK',
        r'(?i)பாரதிய\\s*ஜனதா\\s*கட்சி': 'BJP',
        r'(?i)\\bD\\.?M\\.?K\\.?\\b': 'DMK',
        r'(?i)\\bA\\.?I\\.?A\\.?D\\.?M\\.?K\\.?\\b': 'AIADMK',
        r'(?i)\\bB\\.?J\\.?P\\.?\\b': 'BJP',
        r'(?i)\\bT\\.?V\\.?K\\.?\\b': 'TVK',
        r'(?i)\\bP\\.?M\\.?K\\.?\\b': 'PMK',
        r'(?i)\\bD\\.?M\\.?D\\.?K\\.?\\b': 'DMDK',
        r'(?i)\\bN\\.?T\\.?K\\.?\\b': 'NTK',
        r'(?i)\\bV\\.?C\\.?K\\.?\\b': 'VCK',
        r'(?i)\\bM\\.?D\\.?M\\.?K\\.?\\b': 'MDMK',
        r'(?i)\\bC\\.?P\\.?I\\.?\\b': 'CPI',
        r'(?i)\\bC\\.?P\\.?M\\.?\\b': 'CPM',
    }
    for tamil_pattern, eng_abbr in PARTY_MAP.items():
        text = re.sub(tamil_pattern, eng_abbr, text)
    return text

def deep_clean_text(text):"""

# replace "def deep_clean_text(text):" with the above
content = content.replace("def deep_clean_text(text):", normalize_func)

# 2. Inside deep_clean_text, replace the PARTY_MAP loop with a call to normalize_political_parties
old_party_map_code = """    # ── Pass 3: Political Entity Normalization ──
    # Standardize Tamil abbreviations so the multilingual embedding model
    # perfectly aligns Tamil and English articles about the same party.
    PARTY_MAP = {
        r'(?i)\\bதி\\.?மு\\.?க\\b': 'DMK',
        r'(?i)\\bஅ\\.?தி\\.?மு\\.?க\\b': 'AIADMK',
        r'(?i)\\bபா\\.?ஜ\\.?க\\b': 'BJP',
        r'(?i)\\bகாங்கிரஸ்\\b': 'Congress',
        r'(?i)\\bத\\.?வெ\\.?க\\b': 'TVK',
        r'(?i)\\bபா\\.?ம\\.?க\\b': 'PMK',
        r'(?i)\\bதே\\.?மு\\.?தி\\.?க\\b': 'DMDK',
        r'(?i)\\bநா\\.?த\\.?க\\b': 'NTK',
        r'(?i)\\bவி\\.?சி\\.?க\\b': 'VCK',
        r'(?i)\\bம\\.?தி\\.?மு\\.?க\\b': 'MDMK',
        r'(?i)\\bசி\\.?பி\\.?ஐ\\b': 'CPI',
        r'(?i)\\bசி\\.?பி\\.?எம்\\b': 'CPM',
        r'(?i)திராவிட\\s*முன்னேற்றக்\\s*கழகம்': 'DMK',
        r'(?i)அண்ணா\\s*திராவிட\\s*முன்னேற்றக்\\s*கழகம்': 'AIADMK',
        r'(?i)தமிழக\\s*வெற்றிக்\\s*கழகம்': 'TVK',
        r'(?i)பாரதிய\\s*ஜனதா\\s*கட்சி': 'BJP',
        # English variations with and without dots
        r'(?i)\\bD\\.?M\\.?K\\.?\\b': 'DMK',
        r'(?i)\\bA\\.?I\\.?A\\.?D\\.?M\\.?K\\.?\\b': 'AIADMK',
        r'(?i)\\bB\\.?J\\.?P\\.?\\b': 'BJP',
        r'(?i)\\bT\\.?V\\.?K\\.?\\b': 'TVK',
        r'(?i)\\bP\\.?M\\.?K\\.?\\b': 'PMK',
        r'(?i)\\bD\\.?M\\.?D\\.?K\\.?\\b': 'DMDK',
        r'(?i)\\bN\\.?T\\.?K\\.?\\b': 'NTK',
        r'(?i)\\bV\\.?C\\.?K\\.?\\b': 'VCK',
        r'(?i)\\bM\\.?D\\.?M\\.?K\\.?\\b': 'MDMK',
        r'(?i)\\bC\\.?P\\.?I\\.?\\b': 'CPI',
        r'(?i)\\bC\\.?P\\.?M\\.?\\b': 'CPM',
    }
    
    for tamil_pattern, eng_abbr in PARTY_MAP.items():
        # Using regex to catch variations with or without dots (e.g. தி.மு.க or திமுக)
        result = re.sub(tamil_pattern, eng_abbr, result)"""

new_party_map_code = """    # ── Pass 3: Political Entity Normalization ──
    result = normalize_political_parties(result)"""

content = content.replace(old_party_map_code, new_party_map_code)

# 3. Add more skip keywords for health, lifestyle, cooking
old_lifestyle_en = """    # English Lifestyle & Miscellany
    'lottery', 'kerala lottery', 'win news', 'entertainment', 'gaming', 'video game', 'esports',
    'tips', 'tricks', 'recipe', 'food recipe', 'dish', 'ingredient', 'cook', 'baking',
    'recruitment', 'hiring', 'job opening', 'vacancy',"""

new_lifestyle_en = """    # English Lifestyle & Miscellany
    'lottery', 'kerala lottery', 'win news', 'entertainment', 'gaming', 'video game', 'esports',
    'tips', 'tricks', 'recipe', 'food recipe', 'dish', 'ingredient', 'cook', 'baking',
    'health tips', 'lifestyle', 'wellness', 'weight loss', 'home remedies', 'fitness',
    '/lifestyle/', '/health/', '/wellness/', '/fitness/', '/cooking/', '/recipe/',
    'recruitment', 'hiring', 'job opening', 'vacancy',"""

old_lifestyle_ta = """    # Tamil Lifestyle & Miscellany
    'லாட்டரி', 'கேரளா லாட்டரி', 'கேமிங்', 'வீடியோ கேம்',
    'டிப்ஸ்', 'குறிப்புகள்', 'ரெசிபி', 'சமையல்', 'உணவு', 'சாப்பாடு', 'ருசியான', 'சுவையான', 'சிறப்பம்சங்கள்',
    'நியமனம்', 'வேலைவாய்ப்பு',"""

new_lifestyle_ta = """    # Tamil Lifestyle & Miscellany
    'லாட்டரி', 'கேரளா லாட்டரி', 'கேமிங்', 'வீடியோ கேம்',
    'டிப்ஸ்', 'குறிப்புகள்', 'ரெசிபி', 'சமையல்', 'உணவு', 'சாப்பாடு', 'ருசியான', 'சுவையான', 'சிறப்பம்சங்கள்',
    'ஆரோக்கியக் குறிப்புகள்', 'உடல்நலக் குறிப்புகள்', 'லைஃப்ஸ்டைல்', 'வாழ்க்கை முறை', 'டயட்', 'எடை குறைப்பு', 'நல்வாழ்வு',
    'நியமனம்', 'வேலைவாய்ப்பு',"""

content = content.replace(old_lifestyle_en, new_lifestyle_en)
content = content.replace(old_lifestyle_ta, new_lifestyle_ta)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated text_cleaning.py")
