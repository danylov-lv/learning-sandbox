Think about what makes a CSS selector brittle in the first place: it
assumes a fixed path through the DOM to a fixed tag/attribute. What kind of
"reader" doesn't need that assumption at all -- one that's just handed the
raw text and asked what it means?

Look at `harness/llm.py`'s `generate` signature. There's a `format`
parameter. What happens if you ask the model for free text versus asking
it for something the parameter name suggests?
