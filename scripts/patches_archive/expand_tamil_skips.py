import os
import re

base_dir = "/home/owl/text_analytics/project/veritas_lens_alt"
tc_path = os.path.join(base_dir, "ingestion", "tasks", "text_cleaning.py")

with open(tc_path, "r", encoding="utf-8") as f:
    tc_content = f.read()

new_skips = """# ─── Skip Keywords ───
# Keywords to filter out unwanted topics (entertainment, astrology, ayurveda, etc.)
SKIP_KEYWORDS = [
    # English Entertainment & Gossip
    'cinema', 'actor', 'actress', 'movie', 'film', 'box office', 'review', 'trailer',
    'bollywood', 'kollywood', 'tollywood', 'hollywood', 'celebrity', 'gossip', 'tv show',
    'bigg boss', 'big boss', '/photogallery/', '/explanations/',
    '/videos/', '/video/', '/shorts/', '/photos/', '/photo/', '/gallery/', '/web-stories/', '/podcasts/', '/podcast/',
    
    # Tamil Entertainment & Gossip
    'சினிமா', 'நடிகர்', 'நடிகை', 'படம்', 'திரைப்படம்', 'பாக்ஸ் ஆபிஸ்', 'விமர்சனம்', 'ட்ரைலர்', 'டிரெய்லர்',
    'பாலிவுட்', 'கோலிவுட்', 'டாலிவுட்', 'ஹாலிவுட்', 'பிரபலம்', 'கிசுகிசு', 'டிவி ஷோ',
    'சீரியல்', 'விஜய் டிவி', 'சன் டிவி', 'ஜீ தமிழ்', 'பிக்பாஸ்', 'வைரல்',
    'பொழுதுபோக்கு', 'கவர்ச்சி', 'படுக்கையறை', 'உறவு',

    # English Astrology & Remedies
    'astrology', 'horoscope', 'zodiac', 'vastu', 'ayurveda', 'ayurvedic', 'remedy', 'remedies',
    
    # Tamil Astrology & Remedies
    'ஜோதிடம்', 'ராசிபலன்', 'ராசி', 'வாஸ்து', 'ஆயுர்வேதம்', 'பரிகாரம்', 'ஜாதகம்', 'சனிப்பெயர்ச்சி', 'குருப்பெயர்ச்சி',

    # English Sensationalism & Rumors
    'rumor', 'rumours', 'fake news', 'viral video', 'bizarre', 'shocking', 'scandal',
    
    # Tamil Sensationalism & Rumors
    'வதந்தி', 'போலி செய்தி', 'வைரல் வீடியோ', 'அதிர்ச்சி', 'சர்ச்சை', 'ஸ்கேண்டல்', 'பகீர்',

    # English Lifestyle & Miscellany
    'lottery', 'kerala lottery', 'win news', 'entertainment', 'gaming', 'video game', 'esports',
    'tips', 'tricks', 'recipe', 'food recipe', 'dish', 'ingredient', 'cook', 'baking',
    'recruitment', 'hiring', 'job opening', 'vacancy',
    
    # Tamil Lifestyle & Miscellany
    'லாட்டரி', 'கேரளா லாட்டரி', 'கேமிங்', 'வீடியோ கேம்',
    'டிப்ஸ்', 'குறிப்புகள்', 'ரெசிபி', 'சமையல்', 'உணவு', 'சாப்பாடு', 'ருசியான', 'சுவையான', 'சிறப்பம்சங்கள்',
    'நியமனம்', 'வேலைவாய்ப்பு',

    # English Tech & E-commerce
    'unboxing', 'specifications', 'price in india', 'smartphone review', 'phone review', 'gadget review', 'hands-on', 'hands on', 'first look',
    'offer', 'discount', 'amazon sale', 'flipkart sale', 'recharge plan', 'data plan', 'telecom plan', 'jio plan', 'airtel plan', 'vi plan', 'broadband plan',
    'mobile', 'smartphone', 'smartphones', 'smart tv', 'prepaid', 'postpaid', 'validity', 'bsnl', 'vodafone', 'idea', 'jio', 'airtel', 'vi', 'launch',
    
    # Tamil Tech & E-commerce
    'அன்பாக்சிங்', 'இந்திய விலை', 'ஸ்மார்ட்போன் விமர்சனம்', 'போன் விமர்சனம்',
    'ஆஃபர்', 'சலுகை', 'தள்ளுபடி', 'அமேசான் சேல்', 'பிளிப்கார்ட் சேல்', 'ரீசார்ஜ்', 'டேட்டா திட்டம்', 'டெலிகாம்', 'ஜியோ திட்டம்', 'ஏர்டெல் திட்டம்', 'வி திட்டம்', 'பிராட்பேண்ட்',
    'மொபைல்', 'ஸ்மார்ட்போன்', 'ஸ்மார்ட் டிவி', 'ப்ரீபெய்ட்', 'போஸ்ட்பெய்ட்', 'வேலிடிட்டி', 'பிஎஸ்என்எல்', 'வோடபோன்', 'ஐடியா', 'ஜியோ', 'ஏர்டெல்', 'அறிமுகம்'
]

FESTIVAL_KEYWORDS = [
    'festival', 'diwali', 'deepavali', 'pongal', 'navratri', 'pooja', 'pujan',
    'பண்டிகை', 'தீபாவளி', 'பொங்கல்', 'நவராத்திரி', 'பூஜை', 'திருவிழா', 'விநாயகர்', 'சதுர்த்தி', 'கிருஷ்ண', 'ஜெயந்தி'
]"""

# Replace everything from "# ─── Skip Keywords ───" to the end of FESTIVAL_KEYWORDS block
import re
pattern = re.compile(r"# ─── Skip Keywords ───.*?FESTIVAL_KEYWORDS = \[[^\]]*\]", re.DOTALL)
tc_content = pattern.sub(new_skips, tc_content)

with open(tc_path, "w", encoding="utf-8") as f:
    f.write(tc_content)

print("Updated Skip Keywords!")
