import json
import os
import re
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# 1. إعداد المسارات
# Model is pulled from Hugging Face Hub on first run and cached under
# ~/.cache/huggingface; no local copy required.
# Admin can override via MODEL_HUB_ID env var (set by /api/admin/model). The
# admin endpoint also calls importlib.reload(predict) so this module re-imports
# with the new id and reloads the tokenizer/model.
MODEL_PATH = os.environ.get("MODEL_HUB_ID", "ghaida75/arabert-emotions-7class")
device = "cuda" if torch.cuda.is_available() else "cpu"

# 2. تحميل ملف الترقيم
with open("label_mapping.json", "r", encoding="utf-8") as f:
    mappings = json.load(f)
    id2label = {int(k): v for k, v in mappings["id2label"].items()}

# 3. تحميل المودل والـ Tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
model.to(device)
model.eval()

def clean_arabic_text(text):
    """دالة التنظيف الشاملة المطابقة لكود Colab الخاص بكِ"""
    if not isinstance(text, str):
        return ""

    # 1. إزالة الروابط
    text = re.sub(r"http\S+|www\S+|https\S+", "", text)
    # 2. إزالة المنشنز
    text = re.sub(r"@\w+", "", text)
    # 3. إزالة الهاشتاق
    text = re.sub(r"#", "", text)

    # 4. إزالة الإيموجي
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)

    # 5. إزالة الأرقام
    text = re.sub(r"[0-9٠-٩]", "", text)
    # 6. إزالة التمديد (التطويل)
    text = re.sub(r"(.)\1{2,}", r"\1\1", text)
    # 7. إزالة الرموز
    text = re.sub(r"[^\u0600-\u06FFa-zA-Z\s]", " ", text)

    # 8. تطبيع الحروف (خطوة مهمة جداً للدقة)
    text = re.sub(r"[أإآا]", "ا", text)
    text = re.sub(r"[ىي]", "ي", text)
    text = re.sub(r"ة", "ه", text)

    # 9. إزالة التشكيل وتحويل الإنجليزي لـ lowercase
    text = re.sub(r"[\u064B-\u065F]", "", text)
    text = text.lower()
    # 10. إزالة المسافات الزائدة
    text = re.sub(r"\s+", " ", text).strip()

    return text

def predict_emotion(text: str):
    """توقع الشعور باستخدام النص المنظف"""
    cleaned = clean_arabic_text(text)
    
    # تحويل النص لأرقام (Tensors)
    enc = tokenizer(cleaned, padding=True, truncation=True, max_length=128, return_tensors="pt").to(device)
    
    with torch.no_grad():
        logits = model(**enc).logits
    
    probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]
    pred_id = int(np.argmax(probs))
    
    return {
        "emotion": id2label[pred_id],
        "intensity": round(float(probs[pred_id]), 2),
        "all_scores": {id2label[i]: round(float(probs[i]), 3) for i in range(len(probs))}
    }
    