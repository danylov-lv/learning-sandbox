# Hint 1

Start with the dependency, not the hook -- everything else builds on it
being wired correctly first.

- Read `given/queue-chart/Chart.yaml`, `values.yaml`, and
  `templates/_helpers.tpl` before writing anything. It's small on purpose.
  Notice the named template it defines and how it computes the Service
  name -- you're going to call that same named template from your own
  chart's Deployment/Job templates.
- `Chart.yaml`'s `dependencies:` entry needs four fields: `name`,
  `version`, `repository` (a `file://` path to the sibling chart), and
  `condition` (a dotted path into *your* `values.yaml` that turns the whole
  subchart on/off). After adding it, `helm dependency build` (run from
  inside `chart/`) has to succeed before `helm template` will even attempt
  to render the dependency's resources.
- For the hook: a Job with the three `helm.sh/hook*` annotations is enough
  structure to satisfy the validator's annotation check even before the
  seeding logic inside it works. Get the shape right first, then make the
  script inside actually talk to redis.
- For the diff task: `helm template` doesn't need a cluster at all. Try it
  right now, before you've written anything else, with two different
  `--set` flags and see what changes.
