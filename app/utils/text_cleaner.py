import spacy
import re

# Load multilingual model
nlp = spacy.load("xx_ent_wiki_sm")

def clean_arabic_text(text: str) -> str:
    # Remove entities (names, locations, organizations)
    doc = nlp(text)
    cleaned = text
    
    # Replace named entities with placeholder
    for ent in reversed(doc.ents):
        if ent.label_ in ["PER", "LOC", "ORG", "GPE"]:
            cleaned = cleaned[:ent.start_char] + "[REMOVED]" + cleaned[ent.end_char:]
    
    # Remove numbers
    cleaned = re.sub(r'\d+', '', cleaned)
    
    # Remove email addresses
    cleaned = re.sub(r'\S+@\S+', '', cleaned)
    
    # Remove phone numbers
    cleaned = re.sub(r'[\+\d]?(\d{2,3}[-\.\s]??\d{2,3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4})', '', cleaned)
    
    # Remove emojis
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F9FF"
        u"\U00002600-\U000027BF"
        u"\U0001FA00-\U0001FA6F"
        u"\U0001FA70-\U0001FAFF"
        "]+", flags=re.UNICODE)
    cleaned = emoji_pattern.sub('', cleaned)
    
    # Clean extra spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned

def validate_arabic_text(text: str) -> bool:
    # Check if text contains Arabic characters
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    return bool(arabic_pattern.search(text)) 