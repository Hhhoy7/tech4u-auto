# TECH4U Auto — أتمتة فيديوهات يوتيوب يومياً

موضوع ← سيناريو (Claude) ← تعليق صوتي (ElevenLabs) ← لقطات (Pexels) ← مونتاج (ffmpeg)
← ترجمة عربية متزامنة ← صورة مصغرة ← رفع على يوتيوب. يعمل يومياً عبر GitHub Actions.

## تجربة بدون أي مفاتيح
    pip install -r requirements.txt && bash scripts/get_fonts.sh
    python src/main.py --dry-run        # الناتج في output/<التاريخ>/

## الإعداد (مرة واحدة)
1. **المفاتيح** (GitHub → Settings → Secrets → Actions):
   `ANTHROPIC_API_KEY`، `ELEVENLABS_API_KEY`، `ELEVENLABS_VOICE_ID` (صوت عربي رجالي)، `PEXELS_API_KEY` (مجاني).
2. **يوتيوب**: في Google Cloud فعّل *YouTube Data API v3*، أنشئ OAuth Client من نوع Desktop،
   ثم شغّل محلياً `python scripts/auth_youtube.py client_secret.json` وانسخ
   `YT_CLIENT_ID` و`YT_CLIENT_SECRET` و`YT_REFRESH_TOKEN` إلى الـ Secrets.
   ⚠️ مشاريع API غير الموثّقة تُرغَم على جعل الفيديوهات **خاصة**؛ قدّم طلب *API Audit* لتفعيل النشر العام.
3. ارفع المجلد إلى مستودع GitHub (خاص). التشغيل اليومي في `.github/workflows/daily.yml`،
   ويمكن تشغيله يدوياً من تبويب Actions.

## التحكم
- `topics.json`: طابور المواضيع (الأول يُستهلك أولاً)؛ إذا فرغ يقترح Claude موضوعاً جديداً.
- `config.yaml`: المدة، الصوت، الموسيقى، وضع النشر (`private` للمراجعة ← `scheduled` ← `public`).
- حصة الرفع: ~1600 وحدة من 10000 يومياً، تكفي لفيديو واحد يومياً.

## حدود يجب معرفتها
- لا تُسجَّل شاشة الأدوات تلقائياً؛ المشاهد لقطات ستوك + عناوين. للقطات حقيقية للأدوات ضع ملفاتك في
  مشهد محدد (تطوير لاحق) أو اجعل الفيديو الأول يدوياً.
- محتوى مولّد بالكامل قد يُصنَّف "مُنتَج بكثرة/متكرر" ويفقد أهلية الربح؛ ابدأ بوضع `private` وراجع كل فيديو.
- يوتيوب يشترط الإفصاح عن المحتوى الصناعي الواقعي (مفعّل في الإعدادات).
