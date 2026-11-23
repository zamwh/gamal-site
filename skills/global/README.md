# Sales Skills Library (v1)

A reusable, model-agnostic sales skill library for AI agents. These are original operational adaptations of widely known sales frameworks—not copies of proprietary training materials or books.

## Contents
- `SKILL_ROUTER.md`: how an agent chooses and combines skills
- `skills/00_sales_foundations.md`: universal conversation principles
- `skills/01_spin_discovery.md`: needs discovery through structured questioning
- `skills/02_challenger_insight.md`: useful reframing without arrogance
- `skills/03_sandler_consultative.md`: trust, mutual fit, clear next steps
- `skills/04_persuasion_ethically.md`: influence principles with guardrails
- `skills/05_product_matching.md`: match an offer to verified customer needs and available products
- `skills/06_product_presentation.md`: present options and value clearly
- `skills/07_objection_handling.md`: diagnose and respond to objections
- `skills/08_closing_and_commitment.md`: help customers decide and agree on a next step
- `skills/09_follow_up.md`: purposeful, respectful follow-up
- `skills/10_truth_and_trust.md`: factuality, transparency, and customer protection
- `SOURCES.md`: public references

## Integration notes
Load the router and foundational skill, then retrieve only the skills relevant to the current conversation. Avoid sending every skill to the model on every turn. Keep verified catalog, price, inventory, policies, and customer data outside skill files; expose them through controlled tools/API calls.

Skills are instructions and guidance, not proof of facts. They must never override product data, policies, safety controls, or customer intent.

## Iteration
Use real business observations and owner-approved examples later to adapt local phrasing and customer patterns. Do not infer local market behavior without evidence. Store candidate lessons separately, review them, version them, and only then promote them into skills.
