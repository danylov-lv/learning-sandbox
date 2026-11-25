A concrete walk-through of the shape, without writing the Python for you:

1. Before opening the group, you need somewhere to put each item's task
   handle such that you can later recover which handle belongs to which
   input position -- the return-order guarantee (guarantee 1) depends on
   this. A list built in the same order as `items`, one slot per item,
   works well; a dict keyed by index works too. Decide this before you
   start spawning, not after.

2. Open the group: `async with asyncio.TaskGroup() as tg:`. Everything that
   spawns children happens inside this block.

3. Inside the block, loop over `items` in order and spawn one task per item
   via the group's own task-creation method (not bare `asyncio.
   create_task`), passing it the coroutine `worker(item)`. Store each
   returned handle in the structure from step 1, at the position
   corresponding to that item's place in the input list.

4. That's the entire body of the `async with` block -- just the spawning
   loop. Do not `await` the individual handles inside the block yourself;
   the block's own exit is what waits for everything, and it's also what
   detects a failure and cancels the rest. Awaiting a handle yourself
   inside the block, before the group has had a chance to react to a
   sibling failure, works against what the group is doing for you.

5. After the `async with` block exits *without raising*, every task has
   completed successfully (if any had failed, the block would have raised
   the ExceptionGroup instead of falling through to here). Now go back over
   your stored handles, in the same input order as step 1, and pull each
   one's result off its handle (there's a method for "give me what this
   task returned, now that it's definitely done"). Build your return list
   from these, in order.

6. If the block *does* raise, decide what `run_fanout` itself does with
   that: let it propagate as-is (simplest, and satisfies guarantee 3
   directly), or catch it and re-raise something narrower. Either is valid
   -- just be deliberate and consistent, and say which you picked in
   `NOTES.md`. Don't try to also build and return a partial results list in
   this branch; a raise means the caller gets an exception, not a value.

Nothing above requires touching `asyncio.gather`, `asyncio.wait`, or bare
`asyncio.create_task` at all -- the TaskGroup replaces all three.
