# Voice salesman (GPT-Live) — prototype

Status: built 2026-11-26 for the owner's test. On for everyone since 21:10 (only the owner and the shop owner use it in
the test phase). The owner switches it off and on from the admin, «أداء المساعد والتكلفة» → «إيقاف / تشغيل المساعد
الصوتي» (`voice.public`). While it is off, staff signed in to `/admin` still see the microphone, and are told in the chat
why it is hidden when it is. Staff testing is limited only by the day's voice cap.

## How a call works
1. The customer taps the microphone in the chat. The browser asks for microphone permission; if refused, the chat says he can type.
2. The browser makes a WebRTC offer and posts it to `/api/voice/open`. The server forwards it to OpenAI (`POST https://api.openai.com/v1/live/sessions`, model `gpt-live-1`, client delegation) with the shop's key and returns the answer. The key never reaches the browser.
3. GPT-Live listens and speaks. For anything about pieces, prices, stock or the shop's rules it delegates (`session.delegation.created`). The browser sends the customer's words to `/api/voice/delegate`; the same assistant as the text chat answers (same tools, rules and checker, same chat session and customer file). The cards and the purchase step appear in the chat; the checked answer goes back to GPT-Live with `session.commentary.append` to be said aloud.
4. Cost control: when the customer and the assistant are both quiet for `close_after_ms` (2.5 s) the call closes (`session.close`). A speech detector in the browser (speech band 300–3400 Hz, well above the learned room noise, at least 250 ms) reopens it the moment the customer speaks again; it costs nothing while closed. A reopened call gets the recent conversation and does not greet again.
5. The call is billed per second, at least 15 s per opening (OpenAI's WebRTC minimum). The server measures it from its own clock; a phone that vanishes is closed by a sweeper up to its last heartbeat + 10 s.

## The call screen (2026-11-26, night)
Tapping the microphone opens a stage over the bottom of the chat (the typing bar steps aside; the messages and the
piece cards stay visible above it). A liquid-gold orb, drawn on one small canvas (at most 2x pixels, about 60 frames a
second, half that while the call sleeps, a still frame for phones set to reduce motion):
- flies out of the microphone and lands in the middle (and flies back when the call ends);
- a gold arc rings around it while the first call connects;
- swells softly with the customer's voice (the room's noise barely moves it);
- glows and sends out rings with the assistant's voice (the call's own sound level from WebRTC statistics; a calm
  speech rhythm where a phone gives no level);
- a light sweeps across it while the shop's assistant looks for pieces («لحظة أشوف لك…»);
- rests smaller and dimmer while the call sleeps between sentences («أول ما تتكلم، أرجع أسمعك»).
One button: «إنهاء المكالمة». Staff see OpenAI's own reason in the chat when a call is refused, and keep the microphone.

## Standby and the three voices (2026-11-26, 21:00, the owner's choice)
- **Standby instead of closing:** the call stays connected while nobody talks. After 8 s without words OpenAI pauses
  it (`idle_timeout_s`, `session.paused`) and bills the lower rate ($0.02/min instead of $0.05); it wakes on real speech
  (`wake_policy` speech, threshold 0.6, `session.resumed`), so no first words are lost. After a full minute of quiet the
  call closes completely and the phone's own detector reopens it (the old way). The phone reports the paused time in
  each heartbeat and at the end; the server never accepts more than the call's own time, and bills it at 2¢/min.
  If OpenAI refuses the standby settings the call opens without them and closes after 2.5 s of quiet as before.
  The stage shows standby as a resting orb and «تكلّم متى ما حبيت، أنا معك».
- **Three voices, each with its own name** (the customer chooses with «تغيير الصوت» next to «إنهاء المكالمة»; the
  choice is remembered on that phone; during a call it reconnects with the new voice in about a second):
  «سالم» `echo` (deep, the default) · «فارس» `ballad` (warm) · «ريم» `coral` (woman). (First set, 21:00: ash / verse / marin.) The assistant introduces
  itself by that name once, and «ريم» speaks of herself in the feminine.

## Test mode, budget, dialect (2026-11-26, 21:20, after the owner's test)
- Changing the voice ended the call with "busy": the owner (not signed in) had used a customer's 10¢ for the day, so the
  reconnect was refused. Now `test_mode` (on, with a button in the admin next to the on/off button): no per-person
  limit and no openings limit, only the day's cap; any refusal says why in the chat; the microphone stays. Changing
  the voice also hands the old call back at once, so the new one never waits on it.
- A stated budget: the pieces closest to it first (never above it), not the cheapest (`search_products`, also for
  voice). "The cheapest" when asked still works.
- Dialect: Yemeni or Gulf only, in words and pronunciation; Levantine and Egyptian words are banned by name, in the
  voice instructions and in the text assistant's.

## Owner's test, 21:26: repeats, budget, loudness, voices
- The same necklace came back three times when he asked for something else: the checker's fallback cards ignored the
  pieces already shown, and "شيء آخر / ما عجبني / بديل..." were not read as "something else". Both fixed.
- A 10 million budget for necklaces showed 4 million: the asked kind now comes first and, inside it, the closest to the
  budget; when even the highest is far below the budget the assistant says so plainly and offers to reach the budget
  (a second piece, or a full set).
- Too quiet on iPhone (Safari plays a call quietly or from the earpiece while the microphone is on): on iPhone the
  assistant plays through a louder path (gain 2.4 with a limiter); if no sound comes through it within 1.5 s of
  speech, the plain playback takes over. The audio session is set to play-and-record during the call.
- Still too quiet (21:50): on iPhone the louder path now runs on a fresh audio context made when the call's sound
  arrives (known WebKit workaround: it brings the sound back from the earpiece to the loudspeaker), gain 4 (about
  +12 dB) with a limiter that only stops clipping; then the context made at the tap; then the plain playback. In the
  test phase the chat says once which way the voice plays on that phone. iPhone also keeps a separate call volume:
  the side volume buttons during the call raise it.
- New voices: «سالم» `echo` (deep, default), «فارس» `ballad` (warm), «ريم» `coral` (woman).

## The selling order, picks and checkout (2026-11-26, 22:10, the owner's flow; text and voice)
- Understand first, one question a turn, each asked once, skipped when already said (`agent._discovery`, no model,
  free): to wear or to save? -> to wear: daily, or eye-catching for an occasion? (skipped when kind and budget are both
  given) -> the kind (from what the shop has) -> the budget or the weight. Then it shows, inside the budget/weight.
  "Anything you choose" skips the questions. To save: gold pounds at today's price, how many the budget buys, and the
  sales team on WhatsApp. (Pounds and bullion as stock come later.)
- "Add it to my picks" (`_add_pick`): the piece he means goes to his picks in his browser (`add_picks`), with the new
  total and what is left of his budget, and an offer to complete it with another kind; "complete the budget" searches
  only inside what is left.
- "Let's complete the purchase" (`_checkout`): his picks, their weight and total, then how to buy (WhatsApp with the
  pieces, deposit, final price on the day) and where to collect (the shop, hours).
- Greeting and the chat's welcome ask «تبغى الذهب للبس ولا للادخار؟». Written replies with Levantine/Egyptian words are
  caught by the checker (`dialect`) and rewritten; «إيه» is banned in voice and text.
- Voice: the customer's own words are no longer shown in the chat (speech-to-text misheard him: «طيب», «إيه»). On the
  louder iPhone path the line to OpenAI carries silence while the assistant talks (it heard itself through the
  speaker), unless the customer clearly talks over it (6x the echo's level for 0.3 s).

## Flexible budget and fewer waiting words (2026-11-26, 22:45)
- Nothing inside the budget (or the weight): the closest pieces are shown anyway, with how much they go over
  (`over_budget` / `over_by`, `over_weight` / `over_weight_g`), and the reply says it honestly and asks whether he can add
  a little or wants a lighter kind. The reply without the model says it too.
- Voice waiting words: «لحظة أشوف لك» only for a new request; «لحظة من فضلك» (or nothing when quick) for the piece already
  being discussed; never the same one twice in a row, never before every reply. OpenAI's automatic "one moment" now
  waits 800 ms (its maximum) and the phone hands the request over after 350 ms (was 700), so quick answers come
  without any. The stage shows «يجهّز لك…» while it looks.

## Cost leak fixed (2026-11-27, 00:55): the owner paid about $1 for under 5 minutes of talking
- Likely cause: calls stayed open far longer than the talking. Standby is billed too (2¢/min), the full close after
  60 s of quiet could be reset forever by room noise (the phone's own detector), and noise/echo kept OpenAI active
  (5¢/min). Test mode had no per-person cap.
- Now: standby after 5 s without words (the minimum); the call closes 20 s after OpenAI itself pauses it, whatever
  the room's noise; also after 40 s without any words, and one opening is at most 5 minutes; waking needs clearer speech
  (0.7). The call screen shows, in the test phase, this call's cost and the whole day's voice cost, from the server.

## Caps (settings key `voice`)
| Setting | Default | Meaning |
|---|---|---|
| `per_customer_usd` | 0.10 | most one customer can cost in a day |
| `buyer_usd` | 0.25 | once he is buying (the assistant offered the purchase step) |
| `daily_usd` | 1.5 | all voice calls in a day |
| monthly | 133 (shared) | the text assistant's monthly cap; voice costs are logged in the same `ai_usage` ledger |
| `close_after_ms` | 2500 | quiet time before a call closes |
| `max_call_s` | 300 | longest single opening (5 minutes); speaking again reopens it |
| `max_live` / `opens_per_10min` | 3 / 10 | calls open at once / openings per customer in 10 minutes |
| `standby` / `standby_after_s` / `standby_close_s` | on / 5 / 20 | standby after 5 s without words; full close after 20 s in standby |
| `standby_per_min` / `wake_threshold` | 0.02 / 0.7 | OpenAI's standby rate / how sure it must be that it is speech |
| `ack_delay_ms` | 800 | pause before GPT-Live says "one moment" while the shop's assistant looks (OpenAI allows 0–800) |

Staff testing from `/admin` is limited only by the daily cap.

If OpenAI refuses an optional setting (the voice name, the pause above) the call is retried once without it, and the
owner gets a Telegram note. Every different refusal is reported once a day.

When a cap is reached the assistant says only: «المساعد الصوتي مشغول الحين، كمّل معي كتابة هنا أو كلم فريق المبيعات على الواتساب» and the microphone disappears; the text chat continues.

## Files
- `voice.py` — sessions, caps, delegation, costs, report (table `voice_calls`).
- `web.py` — `/api/voice/status|open|delegate|beat|close`.
- `site/js/site.js` (voice section and the call stage), `site/css/v7.css`, `site/index.html` (microphone, stage, audio).
- `admin.py`, `site/js/admin.js` — the voice box in «أداء المساعد والتكلفة».
- `tests/voice_test.py` — 32 checks against a fake OpenAI endpoint (0–800 ms limit, standby, its cost, the three voices).
- `tests/voice_ui_test.py` — 34 checks of the call screen in a browser, with a fake GPT-Live peer inside the page.
- `web.py` sends `Permissions-Policy: microphone=(self)`; before this fix Chrome and Android blocked the microphone.

## First test (2026-11-26, 20:08)
OpenAI refused the first real call: `acknowledgement_delay_ms` was 900, OpenAI allows at most 800. Fixed (600).

## Open questions for the owner's test
- Does GPT-Live understand the Yemeni dialect well enough? (Arabic is not listed for the API at launch.)
- Which voice: the customer chooses among «سالم», «فارس» and «ريم». OpenAI lists 38 voices; none is Arabic-specific.
- Since 2026-11-19 OpenAI also offers `gpt-live-1.1` (steadier accents). Not used yet (`model` setting).
- The first words after a pause can be lost while the call reopens (about a second): the assistant says «تفضل، معك» and the customer repeats.
