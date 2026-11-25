Work checkpoint by checkpoint, in order — do not try to write all of
`DESIGN.md` in one sitting before running any validator.

Start with CP1. Read the "Capacity model contract" section of `README.md`
slowly, once, before writing any code — every function in
`src/estimate.py` is arithmetic over `workload.json`, nothing more, but
several of them depend on intermediate quantities (like
`daily_new_rows_effective` or `per_pod_capacity`) that more than one
function needs. Work those intermediate quantities out on paper (or in a
scratch script) before touching the stubs, so you are not recomputing the
same thing five different ways across five functions.

Only after `validate_cp1.py` passes should you move on to the CP1 prose
sections of `DESIGN.md` — actually, most people find it easier to write
"Workload characterization" and "Capacity model" WHILE the arithmetic is
fresh, then come back and implement the functions. Either order works;
just do not leave the numeric gate for last, since a design document that
makes claims your capacity model contradicts is a bad sign, not a
coincidence.

Do not think about ADRs, failure modes, or the hostile review until CP1
is green. Each checkpoint exists so you are not holding the entire
capstone in your head at once.
