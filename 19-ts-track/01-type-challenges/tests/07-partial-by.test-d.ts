import type { Expect, Equal } from "@sandbox19/harness";
import type { PartialBy } from "../src/07-partial-by";

interface Config {
  host: string;
  port: number;
  secure: boolean;
}

type TwoOfThree = PartialBy<Config, "host" | "port">;

// The untouched key keeps its exact original (required, non-widened) type.
type _SecureStillRequiredType = Expect<Equal<TwoOfThree["secure"], boolean>>;

// A widened key still reports its original value type when present, plus undefined.
type _HostWidenedType = Expect<Equal<TwoOfThree["host"], string | undefined>>;

// The keys named by K may be omitted entirely...
const _widenedOmissionOk: TwoOfThree = { secure: true };

// ...but the untouched key may not.
// @ts-expect-error — "secure" was not selected by K, so it must stay required
const _missingRequired: TwoOfThree = { host: "x", port: 1 };

type SingleKey = PartialBy<Config, "secure">;
type _HostUnaffected = Expect<Equal<SingleKey["host"], string>>;
type _PortUnaffected = Expect<Equal<SingleKey["port"], number>>;
const _secureOmissionOk: SingleKey = { host: "a", port: 1 };
// @ts-expect-error — "host" was not selected by this K, so it must stay required
const _hostMissing: SingleKey = { port: 1, secure: true };

type AllKeys = PartialBy<Config, keyof Config>;
const _allKeysOmissionOk: AllKeys = {};

type NoKeys = PartialBy<Config, never>;
// @ts-expect-error — K is empty, so nothing became optional; every key stays required
const _noneWidened: NoKeys = {};
