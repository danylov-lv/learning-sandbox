"""t13 CP2 -- the torch model: title tokens -> predicted category.

This module defines the neural network's shape only. The tokenization,
vocabulary building, dataset/dataloader, training loop, and evaluation live
in `src/train.py`; this file is just the `nn.Module`.

No solution is provided anywhere in this task -- work it out from this
docstring, the README, and the hints.
"""

import torch
import torch.nn as nn


class TitleClassifier(nn.Module):
    """A small bag-of-tokens classifier: embed each token, pool the title's
    tokens into one fixed-size vector, then a linear layer (optionally with
    a hidden layer) over that vector produces one logit per category.

    This is deliberately the simplest architecture that can use word
    identity at all -- no recurrence, no attention, no positional
    information. Titles here are short (4 space-separated tokens: brand,
    adjective, noun, model), and a mean-pooled bag of token embeddings is
    plenty of capacity for that; word ORDER carries essentially no signal
    in a title shaped like "<brand> <adjective> <noun> <model>", so nothing
    is lost by ignoring it.

    Suggested shape (you are free to deviate, as long as `forward` maps a
    batch of token-id sequences to a batch of per-class logits):
      - `nn.Embedding(vocab_size, embed_dim, padding_idx=...)` (or
        `nn.EmbeddingBag`, which fuses the embedding lookup and the pooling
        step into one call and is worth reading about) to map token ids to
        dense vectors.
      - Mean-pool (or sum, or use `EmbeddingBag`'s built-in pooling) each
        title's token embeddings into a single fixed-size vector -- titles
        have a variable number of tokens, but the pooled representation is
        always `embed_dim`-wide regardless of title length.
      - A `nn.Linear(embed_dim, num_classes)` (optionally with one hidden
        `nn.Linear` + a nonlinearity like `nn.ReLU` in between) to produce
        one logit per category. Do NOT apply a final softmax here --
        `nn.CrossEntropyLoss` (used in `src/train.py`) expects raw logits
        and applies log-softmax internally.

    Args:
        vocab_size: number of distinct token ids the embedding table must
            cover, including whatever reserved ids you use for padding
            and/or out-of-vocabulary tokens.
        embed_dim: dimensionality of each token's embedding vector. Keep
            this small (e.g. in the tens) -- there is no accuracy benefit
            to a large embedding table on a vocabulary this size, and a
            smaller one trains faster.
        num_classes: number of output logits -- the number of distinct
            categories in the shared dataset (8).
    """

    def __init__(self, vocab_size: int, embed_dim: int, num_classes: int):
        super().__init__()
        raise NotImplementedError

    def forward(self, token_ids: torch.Tensor) -> torch.Tensor:
        """Map a batch of token-id sequences to a batch of per-class logits.

        Args:
            token_ids: a `LongTensor`. The exact shape depends on how you
                chose to batch variable-length titles -- e.g. a padded
                `(batch_size, max_len)` tensor if you pad titles to a
                common length within a batch (in which case make sure your
                pooling step ignores padding positions, e.g. via
                `padding_idx` plus a masked mean, or `EmbeddingBag`'s
                `offsets` argument instead of padding at all).

        Returns:
            A `FloatTensor` of shape `(batch_size, num_classes)` of raw,
            unnormalized logits (no softmax applied).
        """
        raise NotImplementedError
