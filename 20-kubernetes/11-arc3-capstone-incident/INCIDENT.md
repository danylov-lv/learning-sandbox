# Incident Report -- Pipeline Outage in t11

Fill in each section grounded in what you actually observed against this
specific incident (real command output, real object/field names) -- not
generic incident-response prose. This is graded (`tests/validate_cp2.py`):
every section needs real content past the shipped `[fill in` marker, a
minimum length, and this incident's own vocabulary (ConfigMap/envFrom/
REQUIRED_ENV/CrashLoopBackOff -- see hints/hint-3.md if unsure what
"grounded" means here).

## Symptoms observed

[fill in -- what did the on-call actually see, in the order you'd notice
it? Name the specific `kubectl get pods` output, which component(s) showed
`CrashLoopBackOff`, and what the OTHER symptom was that had nothing to do
with a crashing pod (the one you could only find by checking something
other than pod status). Quote real output, not a paraphrase.]

## Root cause

[fill in -- name the exact object, the exact field, and the exact wrong
value. "A ConfigMap was misconfigured" is not specific enough -- which
ConfigMap, which key, what did it say vs. what did the consumers actually
need it to say?]

## Cascade chain

[fill in -- trace, step by step, how ONE wrong value in ONE object turned
into the two separate symptoms you named above. Why did one component
crash while a different component reading the exact same broken ConfigMap
did NOT crash -- what's different about their two REQUIRED_ENV contracts?
Why did the non-crashing component's behavior change anyway, silently,
even though it never restarted or logged an error?]

## How I localized it

[fill in -- what commands did you actually run, in what order, that took
you from "the API is down" to the specific object and field named above?
Name at least one command whose output was the key piece of evidence
(don't just say "I checked the logs" -- what did the log line actually
say, and why did it point at the ConfigMap rather than at the app code?).]

## Prevention

[fill in -- name at least two concrete things that would have caught this
class of bug before it reached a live cluster, or made it visibly wrong
the moment it happened rather than silently wrong. Consider: what CI check
could catch a `ConfigMap` key that doesn't match what a `Deployment`'s
`REQUIRED_ENV` demands, before either is ever applied? What's the
structural difference between wiring a required config key through
`envFrom` (whole-ConfigMap import) versus `env: valueFrom:
configMapKeyRef:` (single named key) that changes how loudly a typo fails
-- and which one would you have used here, knowing what you know now?]
