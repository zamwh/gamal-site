# Voice salesman (GPT-Live) — prototype

Status: built 2026-11-26 for the owner's test. Hidden from customers (`voice.public = false`): only a phone signed in to `/admin` sees the microphone in the chat.

## How a call works
1. The customer taps the microphone in the chat. The browser asks for microphone permission; if refused, the chat says he can type.
2. The browser makes a WebRTC offer and posts it to `/api/voice/open`. The server forwards it to OpenAI (`POST https://api.openai.com/v1/live/sessions`, model `gpt-live-1`, client delegation) with the shop's key and returns the answer. The key never reaches the browser.
3. GPT-Live listens and speaks. For anything about pieces, prices, stock or the shop's rules it delegates (`session.delegation.created`). The browser sends the customer's words to `/api/voice/delegate`; the same assistant as the text chat answers (same tools, rules and checker, same chat session and customer file). The cards and the purchase step appear in the chat; the checked answer goes back to GPT-Live with `session.commentary.append` to be said aloud.
4. Cost control: when the customer and the assistant are both quiet for `close_after_ms` (2.5 s) the call closes (`session.close`). A speech detector in the browser (speech band 300–3400 Hz, well above the learned room noise, at least 250 ms) reopens it the moment the customer speaks again; it costs nothing while closed. A reopened call gets the recent conversation and does not greet again.
5. The call is billed per second, at least 15 s per opening (OpenAI's WebRTC minimum). The server measures it from its own clock; a phone that vanishes is closed by a sweeper up to its last heartbeat + 10 s.

## Caps (settings key `voice`)
| Setting | Default | Meaning |
|---|---|---|
| `per_customer_usd` | 0.10 | most one customer can cost in a day |
| `buyer_usd` | 0.25 | once he is buying (the assistant offered the purchase step) |
| `daily_usd` | 1.5 | all voice calls in a day |
| monthly | 133 (shared) | the text assistant's monthly cap; voice costs are logged in the same `ai_usage` ledger |
| `close_after_ms` | 2500 | quiet time before a call closes |
| `max_call_s` | 240 | longest single opening |
| `max_live` / `opens_per_10min` | 3 / 10 | calls open at once / openings per customer in 10 minutes |

When a cap is reached the assistant says only: «المساعد الصوتي مشغول الحين، كمّل معي كتابة هنا أو كلم فريق المبيعات على الواتساب» and the microphone disappears; the text chat continues.

## Files
- `voice.py` — sessions, caps, delegation, costs, report (table `voice_calls`).
- `web.py` — `/api/voice/status|open|delegate|beat|close`.
- `site/js/site.js` (voice section), `site/css/v7.css`, `site/index.html` (microphone, status bar, audio).
- `admin.py`, `site/js/admin.js` — the voice box in «أداء المساعد والتكلفة».
- `tests/voice_test.py` — 21 checks against a fake OpenAI endpoint.

## Open questions for the owner's test
- Does GPT-Live understand the Yemeni dialect well enough? (Arabic is not listed for the API at launch.)
- Which voice: `cedar` is tried first; if OpenAI rejects it the default voice is used.
- The first words after a pause can be lost while the call reopens (about a second): the assistant says «تفضل، معك» and the customer repeats.
