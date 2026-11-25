Start the app in one terminal and grab its PID before doing anything else:

```
uv run python src/app.py
```

The very first line it prints is `PID=<pid>`. Leave that terminal running --
it needs to stay alive for you to attach to it. Open a second terminal in
the same task directory for the profiler commands below.

`py-spy dump --pid <pid>` is the fastest way to get a first look: it takes
one instantaneous snapshot of every thread's Python call stack and exits
immediately, no SVG, no waiting. Run it two or three times in a row while
the app is running and compare the snapshots.

`py-spy record -o scratch/profile.svg --pid <pid>` samples continuously
until you stop it (Ctrl-C) or it hits a `--duration <seconds>` you pass, and
writes a flamegraph you open in a browser afterward. `scratch/` is
gitignored, so that's where output like this belongs -- don't write it
under `src/`.

If either command reports a permission or access-denied error instead of a
stack/flamegraph: on Windows, py-spy attaching to another process typically
needs matching privilege between the profiler and the target. Close both
terminals, reopen one **as Administrator**, and run both the app and the
py-spy command from there.
