# Hint 1

The two things that eat the evening if you discover them late:

1. **Network path.** The warehouse Postgres lives in docker-compose on
   your host; your workloads live inside kind, which is itself a
   container. "localhost:54306" means three different things across those
   layers. Settle the reachability question first, with a throwaway pod
   and `psql`/`pg_isready`, before writing a single template — a chart
   that renders beautifully but can't reach the database validates
   nothing.

2. **Image path.** kind nodes don't see your host's docker image cache.
   Decide how the image gets into the cluster before you write the
   CronJob template that references it, or you'll be staring at
   `ImagePullBackOff` wondering what's wrong with your YAML (nothing).

For the chart itself: start from the API reference for each of the three
kinds, not from a generated scaffold. A CronJob wraps a Job template
which wraps a pod template — most first-draft mistakes are fields placed
at the wrong nesting level.
