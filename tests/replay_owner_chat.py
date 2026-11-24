"""Replays the owner's real chat of 24 Nov 2026 against the live site and flags banned phrases. Usage: python3 tests/replay_owner_chat.py"""
import json,random,string,urllib.request,re,sys
B="https://ours-dave-grew-servers.trycloudflare.com"
site=json.loads(urllib.request.urlopen(B+"/api/site",timeout=30).read())
print([b.get('addr') or b.get('address') for b in site.get('branches',[])])
P={p["code"]:p for p in site["pieces"]}
sid="evaltest"+''.join(random.choices(string.ascii_lowercase,k=6)); vis="v"+sid
BAD=["ذوقك","اختيارك","اخترت","حضور","تكوين","متناظر","طابع","آخر المتوفر","فريق المبيعات","الدور الأول","رقم 3"]
msgs=["السلام عليكم","وين فروعكم؟","عندكم تشكيلات حلوه صراحة","ابغى سلاسل","بس انا ابغى سلاسل مش طقوم","في غيره ؟","بس انا شايف غيره داخل الموقع!","خلاص جيب لي طقم","كيف عرفت ان ذوقي تراثي ؟"]
for m in msgs:
    r=json.loads(urllib.request.urlopen(urllib.request.Request(B+"/api/chat",json.dumps({"session":sid,"visitor":vis,"message":m}).encode(),{"Content-Type":"application/json"}),timeout=120).read())
    codes=[p["code"] for p in r.get("pieces",[])]
    kinds=[P[c]["kind"] for c in codes if c in P]
    hits=[b for b in BAD if b in r["text"]]
    print("\nزبون:",m,"\nالوكيل:",r["text"],"\nقطع:",[(c,P.get(c,{}).get("title")) for c in codes],"| مخالفات:",hits or "-")
