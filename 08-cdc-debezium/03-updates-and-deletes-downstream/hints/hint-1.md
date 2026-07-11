Each event on `s08.t03.shop.offers` is not a description of what happened
in the abstract -- it's an instruction for what your replica table should
look like next. Think of `op` as telling you which of two things to do:
"make this row look like `after`" or "this row is gone." A snapshot row
looks the same as a brand-new insert from the replica's point of view --
both just mean "here is the current state of this offer_id."

A delete is the odd one out: it doesn't hand you a new state, only the
state that's disappearing. There is nothing to write into the replica for
a delete except "this offer_id is no longer here."
