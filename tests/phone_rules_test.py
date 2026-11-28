"""Pure call-rule tests: no network calls, customer database, or WhatsApp sends."""
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))

import phone

checks = []
def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name, "" if ok else detail)

check("default call is capped at 115 seconds with a 22-second close window",
      phone.call_limits(phone.DEFAULT) == (93, 115), phone.call_limits(phone.DEFAULT))
check("legacy settings above the limit are capped and retain the 22-second window",
      phone.call_limits({"wrap_s": 90, "max_s": 118}) == (93, 115),
      phone.call_limits({"wrap_s": 90, "max_s": 118}))
check("callback call is capped the same way",
      phone.call_limits({"wrap_s": 105, "max_s": 135}) == (93, 115),
      phone.call_limits({"wrap_s": 105, "max_s": 135}))
check("short test calls keep their configured timing",
      phone.call_limits({"wrap_s": 1.2, "max_s": 2.5}) == (1.2, 2.5),
      phone.call_limits({"wrap_s": 1.2, "max_s": 2.5}))

offer = "المستشار: تحب أرسل لك القائمة على الواتساب؟"
check("an explicit yes after the WhatsApp question is consent",
      phone.has_whatsapp_consent([offer, "العميل: نعم، أرسلها"]))
check("a yes without the WhatsApp question is not consent",
      not phone.has_whatsapp_consent(["العميل: نعم"]))
check("a refusal is not consent",
      not phone.has_whatsapp_consent([offer, "العميل: لا شكراً"]))
check("an unclear answer is not consent",
      not phone.has_whatsapp_consent([offer, "العميل: خليني أفكر"]))

class Store:
    def piece_price(self, p):
        return {"total": p["price"]}
class Agent:
    def _available(self):
        return [
            {"type": "سبيكة ذهب", "title": "سبيكة صغيرة", "weight": 5, "price": 250000, "keys": lambda: ["type", "title"]},
            {"type": "جنيه ذهب", "title": "جنيه كامل", "weight": 8, "price": 400000, "keys": lambda: ["type", "title"]},
            {"type": "خاتم", "title": "خاتم ذهبي", "weight": 3, "price": 120000, "keys": lambda: ["type", "title"]},
        ]
p = phone.Phone.__new__(phone.Phone)
p.agent, p.store = Agent(), Store()
options = p._investment_options()
check("investment list uses available bars and pounds with exact stock weights and prices",
      "5 جم" in options and "250,000" in options and "8 جم" in options and "400,000" in options
      and "خاتم" not in options, options)
p.app = type("App", (), {"wa": type("WA", (), {"ready": lambda self: False})()})()
wa_status = p._whatsapp_status()
check("an unlinked WhatsApp account is never described as ready to send",
      "غير مربوط" in wa_status and "لا تعد" in wa_status, wa_status)
check("new collections are mentioned only when the customer context calls for them",
      "لا تذكر التشكيلات الجديدة تلقائياً" in phone.SCRIPT
      and "إذا أبدى اهتماماً بالمشغولات" in phone.SCRIPT, "context rules missing")
check("investment interest uses only available gold bars and pounds and asks consent",
      "إذا ذكر الادخار أو الاستثمار" in phone.SCRIPT
      and "الموافقة يجب أن تأتي صراحة من العميل" in phone.SCRIPT, "investment/consent rules missing")
formatted = phone.SCRIPT.format(name="أحمد", news="خبر", news_line="الذهب نزل", gram="52000 ريال",
                                whatsapp_status=wa_status, investment_options=options)
check("the call script fits all live values without missing placeholders",
      "أحمد" in formatted and "52000 ريال" in formatted and "{name}" not in formatted
      and "{investment_options}" not in formatted)

import voice
check("voice style calls for reactive concise answers and exact supplied figures",
      all(x in voice.PERSONA for x in ("جاوب مباشرة", "أي رقم أو وزن أو سعر", "مستعجل"))
      and "جملة أو جملتين" in voice.TTS_STYLE["m"]
      and "ولا تخمّن" in voice.TTS_STYLE["m"]
      and "جملة أو جملتين" in voice.TTS_STYLE["f"], voice.PERSONA[-700:])

print(f"\n{sum(checks)}/{len(checks)} passed")
sys.exit(0 if all(checks) else 1)
