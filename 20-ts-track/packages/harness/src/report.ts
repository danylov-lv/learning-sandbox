// Repo-wide "print NOT PASSED: <reason> and exit 1, no tracebacks" convention,
// available to any standalone validator script a task might add. Most tasks in
// this module grade via tsc/vitest exit codes instead.

export function notPassed(reason: string): never {
  process.stderr.write(`NOT PASSED: ${reason}\n`);
  process.exit(1);
}

export function passed(msg?: string): void {
  process.stdout.write(`PASSED${msg ? `: ${msg}` : ""}\n`);
}
