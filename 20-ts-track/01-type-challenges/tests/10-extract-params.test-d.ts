import type { Expect, Equal } from "@sandbox19/harness";
import type { ExtractParams } from "../src/10-extract-params";

type _NoParams = Expect<Equal<ExtractParams<"/health">, {}>>;

type _OneParam = Expect<Equal<ExtractParams<"/users/:id">, { id: string }>>;

type _TwoParams = Expect<
  Equal<ExtractParams<"/products/:id/reviews/:rid">, { id: string; rid: string }>
>;

type _ThreeParams = Expect<
  Equal<
    ExtractParams<"/orgs/:orgId/projects/:projectId/tasks/:taskId">,
    { orgId: string; projectId: string; taskId: string }
  >
>;

type _ParamAtRoot = Expect<Equal<ExtractParams<"/:id">, { id: string }>>;

// @ts-expect-error — "rid" is a required param, omitting it must be rejected
const _missingParam: ExtractParams<"/products/:id/reviews/:rid"> = { id: "1" };
