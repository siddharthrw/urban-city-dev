"""Rules: road-design standards turned into data, not code.

rules/active/*.yaml    -- rules the engine (M3) may use. Not necessarily cited: a rule's
                          source.authority can be "placeholder" (an uncited guess, clearly
                          labelled) until the real standard arrives.
rules/proposed/*.yaml  -- rules an LLM extracted from a document, awaiting human review
                          before they can be used.

Nothing here does road design; that is M3. This package only loads, validates, and manages
the rules themselves, and the documents they come from.
"""
