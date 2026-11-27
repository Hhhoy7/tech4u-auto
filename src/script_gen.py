"""توليد السيناريو بصيغة JSON عبر Claude."""
import json, re, datetime
import anthropic
from common import env

SYSTEM = """أنت كاتب سيناريو لقناة يوتيوب عربية تقنية اسمها TECH4U بأسلوب وثائقي سينمائي واثق.
القواعد:
- عربية فصحى مبسّطة، جمل قصيرة تناسب التعليق الصوتي، بلا رموز أو إيموجي داخل النص المنطوق.
- اكتب أسماء المنتجات بالإنجليزية كما هي (ChatGPT, Claude...).
- لا تذكر أرقام إصدارات أو أسعاراً أو إحصاءات إلا إن كنت متأكداً منها؛ فضّل الوصف العام ("الخطة المجانية محدودة، راجع الموقع الرسمي").
- لا تنسب للأدوات قدرات لا تعرفها. الدقة أهم من الإثارة.
- ابدأ بخطاف قوي في أول 15 ثانية، وانتهِ بخلاصة ودعوة للاشتراك دون إلحاح.
- لكل مشهد استعلام بحث إنجليزي قصير (2-4 كلمات) عن لقطة ستوك مناسبة بصرياً (مكاتب، شاشات، مدن ليلية، تقنية، أشخاص يعملون)."""

def generate(topic, cfg, history):
    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    minutes = cfg["video"]["target_minutes"]
    words = minutes * 140
    prompt = f"""الموضوع: {topic}
تاريخ اليوم: {datetime.date.today().isoformat()}
المدة المستهدفة: {minutes} دقائق (≈ {words} كلمة منطوقة إجمالاً، موزّعة على 14-22 مشهداً، كل مشهد 40-90 كلمة).
فيديوهات سابقة للقناة (لا تكرّرها): {json.dumps(history[-15:], ensure_ascii=False)}

أعد JSON فقط بهذا الشكل دون أي نص آخر:
{{
 "title": "عنوان يوتيوب جذاب بالعربية (≤ 70 حرفاً)",
 "thumbnail_text": "نص الصورة المصغرة: 3-5 كلمات كحد أقصى",
 "description": "وصف يوتيوب: ملخص 3 أسطر، ثم قائمة بالأقسام، ثم هاشتاغات",
 "tags": ["..."],
 "scenes": [
  {{"narration": "النص المنطوق", "on_screen_text": "عنوان قصير يظهر على الشاشة (≤ 5 كلمات) أو فارغ", "stock_query": "english query", "chapter": "عنوان الفصل إن بدأ فصل جديد هنا وإلا فارغ"}}
 ]
}}
المشهد الأول فصله "المقدمة"."""
    msg = client.messages.create(model=cfg["llm"]["model"], max_tokens=16000,
                                 system=SYSTEM, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0))
    assert data["scenes"], "سيناريو فارغ"
    return data

def next_topic(cfg_topics, history):
    if cfg_topics["queue"]:
        return cfg_topics["queue"][0], True
    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=load_model(), max_tokens=400,
        messages=[{"role": "user", "content":
            f"اقترح موضوع فيديو واحداً جديداً لقناة TECH4U في مجال: {cfg_topics['niche']}.\n"
            f"تاريخ اليوم {datetime.date.today().isoformat()}. يجب أن يكون الموضوع صالحاً ولا يعتمد على أخبار لا تستطيع التحقق منها.\n"
            f"لا تكرر: {json.dumps(history[-30:], ensure_ascii=False)}\nأجب بسطر واحد فقط: عنوان الموضوع."}])
    return msg.content[0].text.strip(), False

def load_model():
    from common import load_config
    return load_config()["llm"]["model"]
