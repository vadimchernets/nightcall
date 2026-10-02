# Changelog

## 0.3.3 — 2026-10-02

- **Blind comparison** (owner, 01–02.10.2026): when Claude weighs the council, the answers are «Ответ A /
  B / C», no company or model names — an AI judge leans to the answer that sounds like itself.
  `team.py ask --blind DIR` saves the answer without printing who gave it, `team.py blind --dir DIR`
  shows them shuffled as A / B / C, `team.py reveal --dir DIR` names them — only after the decision.
  README «Decisions…», `/nightcall:start` (council) and `/nightcall:team` say so. Test: names hidden
  until `reveal`.
- **429 on a free key → the next provider, not the next key or model of the same account.** Checked in
  the providers' docs 02.10.2026: the free limit is per project (Google AI Studio), per organization
  (Groq), per account (OpenRouter: «Making additional accounts or API keys will not affect your rate
  limits»; NVIDIA). A daily limit pauses it until the end of the run — only that model at Google and Groq
  (their quota is per model too), the whole of OpenRouter (`free-models-per-day` covers every :free
  model); a per-minute limit (all NVIDIA 429s) → the next provider now, this one once more at the end of
  the line, back in `seats.json` a minute later. The roll call still tries every model.

## 0.3.2 — 2026-10-01

- Free keys (the course lesson «Бесплатные ключи ИИ») brought up to date, as in Poly A1 `src/duoAuto.ts`
  (checked live 01.10.2026): **NVIDIA first** (`NVIDIA_API_KEY`, Kimi K3 → GLM-5.3, 30 s per model in the
  roll call), then Google AI Studio (gemini-3.8 / 3.6 / 2.5-flash), Groq (Qwen 3.8, gpt-oss-120b — Llama
  is no longer free), OpenRouter :free (Qwen 3.8, Nemotron 3 Super, `openrouter/free` — no free DeepSeek
  there any more).
- Several models per key: 429/503/404/timeout → the next model of the same key; a key that is not
  accepted (401/403) is out at once; an empty answer → the next model too. The roll call shows which
  model answered. Request and answer as in duoAuto.ts: `max_tokens` 4096 on NVIDIA (Kimi K3 answered
  empty without it), 1500 on Groq, `<think>` and model service tokens (`<|close|>message`) cut out.
- Live roll call 01.10.2026: NVIDIA key — жив (Kimi K3, 1 s); Gemini AI Studio — жив (gemini-3.6-flash,
  3.8-flash gave way).
- Lesson references by name («Бесплатные ключи ИИ»), not «free-keys evenings».

## 0.3.1 — 2026-10-01

- The fence without the old step number 13A — by the lesson name «Забор и машина времени».
