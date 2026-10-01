# Changelog

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
