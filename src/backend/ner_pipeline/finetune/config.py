"""
Veritas Lens — NER Fine-tuning Configuration
=============================================
Central configuration for the fine-tuning pipeline.
"""

import os

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "model")

# --- Model ---
BASE_MODEL_NAME = "google/muril-base-cased"
MAX_SEQ_LENGTH = 256  # RTX 3050 (5.6GB VRAM) friendly

# --- Entity Labels (BIO scheme) ---
# Our target entity types
ENTITY_TYPES = ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "DATE"]

# Build BIO label list: O, B-PERSON, I-PERSON, B-ORGANIZATION, ...
LABEL_LIST = ["O"]
for etype in ENTITY_TYPES:
    LABEL_LIST.append(f"B-{etype}")
    LABEL_LIST.append(f"I-{etype}")

LABEL2ID = {label: i for i, label in enumerate(LABEL_LIST)}
ID2LABEL = {i: label for i, label in enumerate(LABEL_LIST)}
NUM_LABELS = len(LABEL_LIST)

# --- Training Hyperparameters (optimized for RTX 3050 5.6GB) ---
TRAIN_BATCH_SIZE = 8
EVAL_BATCH_SIZE = 16
LEARNING_RATE = 3e-5
NUM_EPOCHS = 10
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.1
FP16 = True
TRAIN_SPLIT = 0.85  # 85% train, 15% validation

# --- Gazetteers ---
# Tamil Nadu political parties (English + Tamil)
POLITICAL_PARTIES = [
    "DMK", "AIADMK", "BJP", "Congress", "INC", "NTK", "PMK", "VCK",
    "MDMK", "CPI", "CPI(M)", "AMMK", "DMDK", "TMC", "MNM",
    "திமுக", "அதிமுக", "பாஜக", "காங்கிரஸ்", "நாதக", "பாமக",
    "விசிக", "மதிமுக", "அமமுக", "தேமுதிக", "திமுகா",
]

# Government bodies
GOVERNMENT_BODIES = [
    "Supreme Court", "High Court", "Election Commission", "Parliament",
    "Legislative Assembly", "Lok Sabha", "Rajya Sabha", "NITI Aayog",
    "RBI", "SEBI", "ISRO", "DRDO",
    "உச்ச நீதிமன்றம்", "உயர் நீதிமன்றம்", "தேர்தல் ஆணையம்",
    "நாடாளுமன்றம்", "சட்டமன்றம்", "மக்களவை", "மாநிலங்களவை",
]

# Known locations (Tamil Nadu districts + major cities)
KNOWN_LOCATIONS = [
    "Chennai", "Madurai", "Coimbatore", "Tiruchirappalli", "Salem",
    "Tirunelveli", "Erode", "Vellore", "Thanjavur", "Dindigul",
    "Kanchipuram", "Cuddalore", "Thoothukudi", "Tiruvannamalai",
    "சென்னை", "மதுரை", "கோவை", "திருச்சி", "சேலம்",
    "திருநெல்வேலி", "ஈரோடு", "வேலூர்", "தஞ்சாவூர்", "திண்டுக்கல்",
    "காஞ்சிபுரம்", "கடலூர்", "தூத்துக்குடி", "திருவண்ணாமலை",
    "India", "Tamil Nadu", "தமிழ்நாடு", "இந்தியா",
]

# Known persons (prominent political figures)
KNOWN_PERSONS = [
    "M.K. Stalin", "Edappadi Palaniswami", "Annamalai", "Rahul Gandhi",
    "Narendra Modi", "Amit Shah", "Udhayanidhi Stalin",
    "மு.க.ஸ்டாலின்", "எடப்பாடி பழனிசாமி", "அண்ணாமலை",
    "ராகுல் காந்தி", "நரேந்திர மோடி", "அமித் ஷா", "உதயநிதி ஸ்டாலின்",
]

# Contextual rule patterns

# Person title prefixes to strip
PERSON_PREFIXES = [
    r"Chief\s+Minister\s+", r"Prime\s+Minister\s+", r"Minister\s+",
    r"President\s+", r"Governor\s+", r"Mr\.\s*", r"Mrs\.\s*",
    r"Ms\.\s*", r"Dr\.\s*", r"Sri\.\s*", r"Shri\.\s*",
    r"முதலமைச்சர்\s+", r"பிரதமர்\s+", r"அமைச்சர்\s+",
    r"ஆளுநர்\s+", r"திரு\.\s*", r"திருமதி\.\s*", r"டாக்டர்\s*",
    r"செல்வி\.\s*",
]

# Location suffixes to strip
LOCATION_SUFFIXES = [
    r"\s+District$", r"\s+City$", r"\s+State$", r"\s+Town$",
    r"\s+மாவட்டம்$", r"\s+ஊராட்சி$", r"\s+ஒன்றியம்$",
    r"\s+மாநகராட்சி$", r"\s+பஞ்சாயத்து$", r"\s+நகரம்$",
    r"\s+பேரூராட்சி$",
]

# Organization suffixes for context-based classification
ORG_CONTEXT_SUFFIXES = [
    "கட்சி", "கழகம்", "அமைப்பு", "குழு", "சங்கம்",
    "நிறுவனம்", "கூட்டமைப்பு", "மன்றம்",
    "Party", "Corporation", "Committee", "Association",
    "Foundation", "Institute", "Board", "Commission",
]

# Location context suffixes for context-based classification
LOC_CONTEXT_SUFFIXES = [
    "மாவட்டம்", "ஊராட்சி", "ஒன்றியம்", "மாநகராட்சி",
    "பஞ்சாயத்து", "நகரம்", "பேரூராட்சி", "மாநிலம்",
    "District", "City", "State", "Town", "Village",
]

# Tamil morphological suffixes (case markers) to strip when matching gazetteers
TAMIL_CASE_SUFFIXES = [
    "இல்", "இன்", "ஐ", "உடன்", "ஆல்", "க்கு", "இடம்",
    "உக்கு", "அது", "இது", "ஆக", "ஓடு", "விடம்",
    "யில்", "யின்", "வில்", "வின்", "த்தில்", "த்தின்",
    "களில்", "களின்", "களை", "கள்",
]
