from predict import predict_emotion

# جملة تجريبية بلهجة سعودية
text = "يا خي والله الشغل اليوم يفتح النفس والبيئة مره مريحة"

print("جاري تشغيل المودل للتحليل...")
try:
    result = predict_emotion(text)
    print("-" * 30)
    print(f"text: {text}")
    print(f" detected emotion: {result['emotion']}")
    print(f"percentage of certainty : {result['intensity'] * 100}%")
    print("-" * 30)
except Exception as e:
    print(f"حدث خطأ أثناء التشغيل: {e}")