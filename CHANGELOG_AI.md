# Changelog — AI assistants (text and voice)

- 2026-11-26 (night) — Voice call screen: a liquid-gold orb stage that opens from the microphone, rings while connecting, reacts to the customer's and the assistant's voices, shimmers while the shop's assistant looks, rests while the call sleeps. Fixed the first real call (OpenAI allows a 0–800 ms acknowledgement delay; we sent 900) and the microphone block on Chrome/Android (Permissions-Policy). Optional settings OpenAI refuses are dropped and retried once; each different refusal is reported once a day; staff testing gets the 25¢ cap.
- 2026-11-26 — Voice salesman prototype (GPT-Live, client delegation to the text assistant), staff-only; closes when quiet and reopens on real speech; caps per customer (10¢, 25¢ when buying), 1.5 $/day, shared monthly cap; per-second cost in the admin. See docs/voice.md.
- 2026-11-26 — Making charge is internal: the customer assistant never states a making amount or splits a price; the checker blocks it.
- 2026-11-26 — Research-based training of the text assistant (router, templates, just-in-time instructions, claim checker); 25 tough scenarios × 5 runs pass.
