"""
AI Prompt Templates — all prompts used by the AI layer.

Each prompt has clear instructions, output JSON schema, and safety constraints.
"""
from __future__ import annotations


PROMPT_TO_SCHEMA = """You are a data schema designer for SynthGen AI.

Convert the user's natural language request into a SynthSchema JSON.

Rules:
1. Output ONLY valid JSON — no markdown, no explanation
2. Every column must have a "kind" from: id, int, num, money, date, datetime, cat, text, bool, fk, email, phone, address, url
3. Use "id" for primary keys, "fk" for foreign keys with a "ref" field like "table.column"
4. Money columns must use integer minor units (cents)
5. Include realistic "weights" for categorical columns
6. Include relationships for multi-table schemas
7. All company/person names must be fictional
8. Email domains must be example.com
9. Account numbers must use invalid patterns

Output format:
{{
  "name": "schema_name",
  "locale": "us",
  "currency": "USD",
  "domain": "retail",
  "tables": [
    {{
      "name": "table_name",
      "rows": 1000,
      "primary_key": "id_column",
      "columns": [
        {{"name": "col", "kind": "type", "nullable": false, ...}}
      ]
    }}
  ],
  "relationships": [
    {{"parent": "parent_table", "child": "child_table", "cardinality": "1:N", "mean_children": 3}}
  ]
}}

User request: {prompt}
"""

SAMPLE_TO_SCHEMA = """You are analyzing a data profile to suggest schema improvements.

Given these column profiles, suggest:
1. Better column types if any are misdetected
2. PII columns that need privacy actions
3. Possible relationships between tables
4. Constraints that should be enforced
5. Edge cases worth testing

Column profiles:
{profile_json}

Output JSON with your suggestions:
{{
  "type_corrections": [{{"column": "...", "current": "...", "suggested": "...", "reason": "..."}}],
  "pii_flags": [{{"column": "...", "level": "direct|quasi", "action": "synthetic|mask|hash"}}],
  "relationships": [{{"column": "...", "likely_ref": "table.column", "confidence": "high|review"}}],
  "constraints": [{{"column": "...", "type": "unique|range|pattern", "details": "..."}}],
  "edge_cases": [{{"type": "...", "reason": "...", "priority": "high|medium|low"}}]
}}
"""

EDGE_CASE_SUGGESTIONS = """Given this table schema, suggest edge cases for testing.

Schema: {schema_json}

For each suggestion, explain WHY it matters for testing:
{{
  "suggestions": [
    {{"type": "...", "columns": ["..."], "reason": "...", "priority": "high|medium|low"}}
  ]
}}
"""

CHAT_REFINE = """You are helping a user refine their synthetic data configuration.

Current schema:
{schema_json}

User instruction: "{instruction}"

Generate a JSON Patch (RFC 6902) to apply the requested changes:
{{
  "patches": [
    {{"op": "replace|add|remove", "path": "/tables/0/rows", "value": 5000}}
  ],
  "explanation": ["Changed row count to 5000 as requested"]
}}
"""

STATEMENT_QUERY_PARSE = """Parse this bank statement request into structured constraints.

Request: "{query}"

Output:
{{
  "period": {{"days": 90}},
  "opening_balance": 120000,
  "constraints": {{
    "min_balance": null,
    "ending_balance": {{"target": null, "tolerance": 5000}},
    "max_transaction": null
  }},
  "recurring": [
    {{"type": "salary|rent|utilities", "day": 1, "amount": 180000, "description": "..."}}
  ],
  "spend_mix": {{
    "groceries": 0.25, "fuel": 0.15, "dining": 0.12
  }}
}}

Note: All amounts in integer minor units (cents). 1200.00 = 120000.
"""

VOCAB_BANK_GENERATE = """Generate {size} fictional but realistic {semantic} values for locale {locale}.

Rules:
- All values must be obviously fictional
- Use culturally appropriate names/values
- Email domains: example.com only
- Phone numbers: use reserved/invalid ranges
- No real company names or brands

Output as a JSON array of strings.
"""
