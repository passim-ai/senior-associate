---
name: setup
description: Set up Senior Associate / Matters for ChatGPT desktop, check its local document tools, choose folders, and explain the privacy hook. Use for installation, setup, or repair of the ChatGPT version.
---

# Set up Senior Associate / Matters

Use a local ChatGPT desktop conversation. This plugin runs through the user's desktop tools and account; it does not need an OpenAI API key. Open its Matters sidebar or call open_matters, then use Settings to choose a dedicated Matters folder (default ~/Matters) and optional model-letter folder. Do not use a general practice-files folder. Reuse the Claude Matters folder when the user wants shared matters; neither client owns an exclusive copy, and both must respect the same leases.

Check uv, Ghostscript, and optionally Poppler and LibreOffice. Install missing dependencies only within the user's setup request and normal host permissions. Never alter the Claude plugin installation, its marketplace, its settings, or its hooks. Your details in the app supplies counsel information; do not invent profile answers.

Show the user this package's chatgpt/hooks.json and chatgpt/privacy_hook.py before they review/trust the exact hook in the host's hook UI. Never change trust records or bypass hook trust programmatically. Explain that the hook observes supported local tools but not hosted web calls; docs/CHATGPT-RUNTIME.md requires an exact-input check before every research request. Do not claim an untested hook is enabled or universally protective.

Verify with the fictional sample first: open it, review the requested action, test a chat handoff, and confirm the runtime's status rather than assuming a button started work. Tell the user what was verified and anything still unavailable. Do not run a real client packet merely to test installation.
