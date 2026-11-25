# EduFlow AI Studio — استوديو الإنتاج التعليمي الذكي

تطبيق ويب (Streamlit + SQLAlchemy) يحوّل مصادر المعلم ومتطلباته إلى عروض PPTX ومستندات وأوراق عمل واختبارات قابلة للتعديل والتصدير.

## التشغيل محليًا
```
pip install -r requirements.txt
streamlit run app.py
```
## الإعدادات (Streamlit secrets أو متغيرات بيئة)
- `DATABASE_URL`: اختياري. افتراضيًا SQLite محلي (غير دائم على الاستضافة المجانية). لقاعدة دائمة استخدم PostgreSQL.
- `APP_SECRET`: مطلوب لحفظ مفاتيح مزودي الذكاء الاصطناعي مشفرة. بدونه لا تُحفظ المفاتيح.
## الاختبارات
`python tests/acceptance.py`
## الحدود
انظر صفحة «حالة النظام» داخل التطبيق. الخط Amiri (SIL OFL) مضمّن لتصدير PDF العربي.
