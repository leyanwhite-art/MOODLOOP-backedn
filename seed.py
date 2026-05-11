from app.database import SessionLocal
from app import models
from app.utils.security import hash_password
from app.utils.crypto import encrypt_text
from datetime import datetime, timedelta
import random

db = SessionLocal()

print("🌱 Starting seed...")

# 1. Create Departments
departments = [
    "Accounting",
    "Maintenance",
    "Human Resources",
    "IT",
    "Sales",
    "Marketing"
]

dept_objects = {}
for dept_name in departments:
    dept = db.query(models.Department).filter(
        models.Department.name == dept_name
    ).first()
    if not dept:
        dept = models.Department(name=dept_name)
        db.add(dept)
        db.commit()
        db.refresh(dept)
    dept_objects[dept_name] = dept
    print(f"✅ Department: {dept_name}")

# 2. Create HR Manager
hr = db.query(models.Employee).filter(
    models.Employee.email == "hr@moodloop.com"
).first()
if not hr:
    hr = models.Employee(
        name="HR Manager",
        email="hr@moodloop.com",
        password_hash=hash_password("Hr@123456"),
        role=models.RoleEnum.hr,
        department_id=None,
        is_verified=True,
        is_active=True,
    )
    db.add(hr)
    db.commit()
    db.refresh(hr)
print(f"✅ HR Manager created: hr@moodloop.com / Hr@123456")

# 2b. Create Admin
admin = db.query(models.Employee).filter(
    models.Employee.email == "admin@moodloop.com"
).first()
if not admin:
    admin = models.Employee(
        name="System Admin",
        email="admin@moodloop.com",
        password_hash=hash_password("Admin@123456"),
        role=models.RoleEnum.admin,
        department_id=None,
        is_verified=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
print("✅ Admin created: admin@moodloop.com / Admin@123456")

# 3. Create Mock Employees
employees_data = [
    ("Ahmed Ali", "ahmed.ali@moodloop.com", "Accounting"),
    ("Sara Mohammed", "sara.mohammed@moodloop.com", "Accounting"),
    ("Khalid Hassan", "khalid.hassan@moodloop.com", "Accounting"),
    ("Fatima Omar", "fatima.omar@moodloop.com", "Accounting"),
    ("Omar Abdullah", "omar.abdullah@moodloop.com", "Accounting"),
    ("Nora Salem", "nora.salem@moodloop.com", "Maintenance"),
    ("Youssef Ibrahim", "youssef.ibrahim@moodloop.com", "Maintenance"),
    ("Layla Khalid", "layla.khalid@moodloop.com", "Maintenance"),
    ("Tariq Mahmoud", "tariq.mahmoud@moodloop.com", "Maintenance"),
    ("Reem Faisal", "reem.faisal@moodloop.com", "Maintenance"),
    ("Hamad Nasser", "hamad.nasser@moodloop.com", "Human Resources"),
    ("Mona Saeed", "mona.saeed@moodloop.com", "Human Resources"),
    ("Saad Turki", "saad.turki@moodloop.com", "Human Resources"),
    ("Hessa Ali", "hessa.ali@moodloop.com", "Human Resources"),
    ("Faris Rashid", "faris.rashid@moodloop.com", "Human Resources"),
    ("Dana Waleed", "dana.waleed@moodloop.com", "IT"),
    ("Majed Fahad", "majed.fahad@moodloop.com", "IT"),
    ("Rawan Ahmed", "rawan.ahmed@moodloop.com", "IT"),
    ("Sultan Meshal", "sultan.meshal@moodloop.com", "IT"),
    ("Noura Fahad", "noura.fahad@moodloop.com", "IT"),
    ("Bader Salem", "bader.salem@moodloop.com", "Sales"),
    ("Lina Khalid", "lina.khalid@moodloop.com", "Sales"),
    ("Waleed Omar", "waleed.omar@moodloop.com", "Sales"),
    ("Ghada Nasser", "ghada.nasser@moodloop.com", "Sales"),
    ("Turki Faisal", "turki.faisal@moodloop.com", "Sales"),
    ("Abdulaziz Ali", "abdulaziz.ali@moodloop.com", "Marketing"),
    ("Shahad Mohammed", "shahad.mohammed@moodloop.com", "Marketing"),
    ("Nawaf Hassan", "nawaf.hassan@moodloop.com", "Marketing"),
    ("Reema Ibrahim", "reema.ibrahim@moodloop.com", "Marketing"),
    ("Fahad Turki", "fahad.turki@moodloop.com", "Marketing"),
]

employee_objects = []
for name, email, dept_name in employees_data:
    emp = db.query(models.Employee).filter(
        models.Employee.email == email
    ).first()
    if not emp:
        emp = models.Employee(
            name=name,
            email=email,
            password_hash=hash_password("Employee@123"),
            role=models.RoleEnum.employee,
            department_id=dept_objects[dept_name].department_id,
            is_verified=True,
            is_active=True,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)
    employee_objects.append(emp)
    print(f"✅ Employee: {name} - {dept_name}")

# 4. Create Mock Reflections (encrypted at rest)
arabic_reflections = [
    "أشعر اليوم بضغط كبير في العمل وأجد صعوبة في إتمام مهامي اليومية بسبب كثرة الاجتماعات والمواعيد النهائية المتراكمة",
    "كان يوماً جيداً بشكل عام وأشعر بالرضا عن ما أنجزته اليوم رغم بعض التحديات البسيطة التي واجهتني في العمل",
    "أشعر بالإرهاق الشديد وعدم القدرة على التركيز بسبب ضغط العمل المتزايد وقلة النوم في الفترة الأخيرة",
    "اليوم كان منتجاً جداً وأشعر بالسعادة لأنني أتممت جميع مهامي في الوقت المحدد وحصلت على تقييم إيجابي",
    "أشعر بالقلق من الاجتماع القادم وأتمنى أن تسير الأمور بشكل جيد وأن يكون الفريق متعاوناً",
    "العمل اليوم كان ممتعاً وأشعر بالحماس والدافعية للاستمرار وتحقيق المزيد من الإنجازات في المشاريع القادمة",
    "أشعر بعدم الارتياح بسبب بعض التعليقات السلبية التي تلقيتها اليوم وأحاول التعامل معها بإيجابية",
    "يوم هادئ نسبياً وأشعر بالاستقرار والتوازن في العمل مما يساعدني على التفكير بوضوح وإنجاز مهامي",
]

for emp in employee_objects:
    num_reflections = random.randint(2, 5)
    for i in range(num_reflections):
        days_ago = random.randint(0, 14)
        hours_apart = i * 3
        reflection_time = datetime.now() - timedelta(days=days_ago, hours=hours_apart)

        plain = random.choice(arabic_reflections)
        reflection = models.DailyReflection(
            employee_id=emp.employee_id,
            department_id=emp.department_id,
            input_text=encrypt_text(plain),
            cleaned_text=encrypt_text(plain),
            created_at=reflection_time
        )
        db.add(reflection)

db.commit()
print(f" Mock reflections created (encrypted)!")

# 5. Create Mock Sentiment Analyses
sentiments = ["positive", "neutral", "negative"]
emotions = ["happiness", "stress", "anger", "motivation", "neutral", "sadness", "cooperation"]

reflections = db.query(models.DailyReflection).all()
for ref in reflections:
    # Skip rows that already have sentiments (idempotent re-runs).
    existing = db.query(models.SentimentAnalysis).filter(
        models.SentimentAnalysis.reflection_id == ref.reflection_id
    ).first()
    if existing:
        continue
    sentiment = models.SentimentAnalysis(
        reflection_id=ref.reflection_id,
        department_id=ref.department_id,
        sentiment=random.choice(sentiments),
        emotion=random.choice(emotions),
        confidence=round(random.uniform(0.65, 0.99), 2),
        analyzed_at=ref.created_at
    )
    db.add(sentiment)

db.commit()
print(" Mock sentiment analyses created!")

# 6. Seed default system_settings rows if migration didn't run yet.
_DEFAULTS = [
    ("alarm_threshold_low", 0.30),
    ("alarm_threshold_medium", 0.50),
    ("alarm_threshold_high", 0.65),
    ("alarm_threshold_critical", 0.80),
    ("alarm_k_anonymity_floor", 5),
    ("reflection_retention_days", 365),
    ("max_reflections_per_day", 3),
    ("reflection_cooldown_hours", 2),
    ("model_hub_id", "ghaida75/arabert-emotions-7class"),
]
for k, v in _DEFAULTS:
    if not db.query(models.SystemSetting).filter(models.SystemSetting.key == k).first():
        db.add(models.SystemSetting(key=k, value=v))
db.commit()
print(" System settings seeded!")

print("\n Seed completed successfully!")
print("\n Login credentials:")
print("Admin     : admin@moodloop.com / Admin@123456")
print("HR Manager: hr@moodloop.com / Hr@123456")
print("Employees : [any employee email] / Employee@123")

db.close()
