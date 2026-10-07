import torch
from transformers import pipeline

class TranslationService:
    def __init__(self):
        self.device = 0 if torch.cuda.is_available() else -1
        self.pipe = None
        
        self.topic_map_en_to_ta = {
            "world_news": "உலக செய்திகள்",
            "politics": "அரசியல்",
            "economy": "பொருளாதாரம்",
            "science_health": "அறிவியல் & சுகாதாரம்",
            "sports": "விளையாட்டு",
            "crime_law": "குற்றம் & சட்டம்",
            "education": "கல்வி",
            "general": "பொது செய்திகள்",
            "News": "செய்திகள்"
        }
        self.topic_map_ta_to_en = {v: k for k, v in self.topic_map_en_to_ta.items()}

    def _load_model(self):
        if self.pipe is None:
            print("Loading NLLB-200 model...")
            self.pipe = pipeline("translation", model="facebook/nllb-200-distilled-600M", device=self.device)
        return self.pipe

    def translate(self, text, target_lang="ta"):
        if not text:
            return text
            
        if target_lang == "ta":
            if any(ord(c) > 2944 and ord(c) < 3071 for c in text):
                return text
            pipe = self._load_model()
            try:
                res = pipe(text, src_lang="eng_Latn", tgt_lang="tam_Taml", max_length=512)
                return res[0]['translation_text']
            except Exception as e:
                print("Translation error:", e)
                return text
                
        elif target_lang == "en":
            if not any(ord(c) > 2944 and ord(c) < 3071 for c in text):
                return text
            pipe = self._load_model()
            try:
                res = pipe(text, src_lang="tam_Taml", tgt_lang="eng_Latn", max_length=512)
                return res[0]['translation_text']
            except Exception as e:
                print("Translation error:", e)
                return text
                
        return text

    def translate_topic(self, topic, target_lang="ta"):
        if not topic:
            return "General"
        if target_lang == "ta":
            return self.topic_map_en_to_ta.get(topic.lower(), topic)
        else:
            return self.topic_map_ta_to_en.get(topic, topic)

translator_service = TranslationService()
