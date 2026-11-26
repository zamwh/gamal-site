## 2026-11-27 — «جداوي»: a turn-by-turn ElevenLabs voice beside the live call
- New voice in «تغيير الصوت»: «جداوي» (Saudi, ElevenLabs). One sentence at a time: recorded on the phone, turned into
  text by OpenAI, answered by the same shop assistant, read by ElevenLabs. No open call, nothing paid while quiet.
- Admin: ElevenLabs key box (kept on the server only), on/off, a test button that plays a sample and shows the credits
  left; the AI tab shows this voice's talks, answers, credits and costs.
- Spoken text: numbers in words (prices, grams, percent), no codes/links/emoji, long answers trimmed for the voice.

# Changelog — AI assistants (text and voice)

- 2026-11-27 (00:55) — Voice cost leak: calls close 20 s after OpenAI's own standby (room noise can no longer keep them open), after 40 s without words, and at 5 minutes; standby after 5 s; wake threshold 0.7; live call and day cost on the call screen (test phase).
- 2026-11-26 (22:50) — Nothing inside the budget or weight: the closest pieces anyway, with the honest difference. Voice: waiting words only when they fit («لحظة أشوف لك» new request, «لحظة من فضلك» same piece), never repeated; automatic acknowledgement at 800 ms, hand-over after 350 ms.
- 2026-11-26 (22:15) — Selling order: understand first (wear/save -> daily/eye-catching -> kind -> budget or weight), one question a turn; add to picks from the conversation, complete the budget inside what is left, checkout with the picks, how to buy and where to collect; saving -> gold pounds. Dialect checker on written replies; voice: customer transcripts hidden, echo guard on the louder iPhone path.
- 2026-11-26 (21:35) — No repeated pieces when the customer asks for something else; the asked kind first and closest to the budget, with an honest note when far below it; louder voice on iPhone (with a safe fallback); new voices echo / ballad / coral.
- 2026-11-26 (21:20) — Voice test mode (no per-person or openings limit, only the day cap; reasons shown; admin button); changing the voice no longer ends the call. A stated budget shows the pieces closest to it first. Yemeni/Gulf dialect only (Levantine and Egyptian words banned) in voice and text.
- 2026-11-26 (21:10) — Voice on for everyone (test phase: the owner and the shop owner), with an on/off button in the admin; staff testing limited only by the day cap; staff are told why the microphone is hidden; the voice state is checked each time the chat opens. Chat chip «وين فروعكم؟» → «وين موقعكم؟» (one shop).
- 2026-11-26 (21:00) — Voice: OpenAI's standby replaces closing on every pause (no lost words; quiet time at 2¢/min; full close after a minute of quiet); standby time is billed at its own rate in the caps. Three named voices for the customer («سالم», «فارس», «ريم») behind «تغيير الصوت»; the assistant takes the chosen name, «ريم» speaks in the feminine.
- 2026-11-26 (night) — Voice call screen: a liquid-gold orb stage that opens from the microphone, rings while connecting, reacts to the customer's and the assistant's voices, shimmers while the shop's assistant looks, rests while the call sleeps. Fixed the first real call (OpenAI allows a 0–800 ms acknowledgement delay; we sent 900) and the microphone block on Chrome/Android (Permissions-Policy). Optional settings OpenAI refuses are dropped and retried once; each different refusal is reported once a day; staff testing gets the 25¢ cap.
- 2026-11-26 — Voice salesman prototype (GPT-Live, client delegation to the text assistant), staff-only; closes when quiet and reopens on real speech; caps per customer (10¢, 25¢ when buying), 1.5 $/day, shared monthly cap; per-second cost in the admin. See docs/voice.md.
- 2026-11-26 — Making charge is internal: the customer assistant never states a making amount or splits a price; the checker blocks it.
- 2026-11-26 — Research-based training of the text assistant (router, templates, just-in-time instructions, claim checker); 25 tough scenarios × 5 runs pass.
