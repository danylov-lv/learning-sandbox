You need to compare each snapshot's price to the *previous* snapshot for the
same product/source, not to any fixed baseline. Think about what "previous
row within a group, in a given order" means in SQL — there's a window
function built exactly for that. A plain self-join on adjacent rows works
too, but it's more code for the same result.
