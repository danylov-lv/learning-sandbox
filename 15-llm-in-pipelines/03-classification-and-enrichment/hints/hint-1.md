The model doesn't know your 8 categories unless you tell it. There is no
implicit shared vocabulary between "a product classifier" in general and
"a product classifier for exactly these 8 department names" -- if the
category list isn't spelled out somewhere in the prompt, the model has to
guess a label from its own general-purpose sense of "product categories,"
which won't reliably line up with your closed set at all.

Separately: think about why a plain keyword match (brand -> category, or
noun -> category) would get fooled here, and what that tells you about
what the model needs to weigh instead of any single word in isolation.
