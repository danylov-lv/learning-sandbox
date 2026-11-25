`XREADGROUP GROUP <group> <consumer> COUNT <n> STREAMS <key> >` is the read
side. The special ID `>` means "give me entries nobody in this group has ever
been delivered before" -- it is not "everything since the beginning" and not
"everything after some timestamp"; it's a strictly-once-per-group delivery
cursor the group itself maintains. As a SIDE EFFECT of that read, Redis adds
every returned entry to the group's PEL under the consumer's name, with a
delivery timestamp and a delivery count. Nothing removes it from the PEL
automatically -- not a timeout, not the next read, nothing -- except `XACK`.

That's the whole story for the happy path: `XREADGROUP >` to get work (PEL
gains entries), do the work, `XACK` the entry IDs you finished (PEL loses
those entries). If a consumer dies between the read and the ack, its entries
just sit in the PEL forever, still attributed to a consumer name that will
never call `XACK` again -- which is precisely the situation your crash
simulation creates on purpose (read via `consume_new`, then simply never call
`ack`). Nothing about that state is broken or an error; it's exactly what a
real crash leaves behind, and it's stable until someone with visibility into
the PEL does something about it.
