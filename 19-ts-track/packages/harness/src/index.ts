// Public surface of @sandbox19/harness. Tasks depend on this — never
// re-implement the mock server or the type utilities.

export type {
  Expect,
  ExpectTrue,
  ExpectFalse,
  Equal,
  NotEqual,
  IsAny,
  IsNever,
  IsUnknown,
  Alike,
} from "./type-testing";

export {
  startMockServer,
  type MockServer,
  type Product,
  type User,
  type ApiError,
} from "./mock-server";

export { notPassed, passed } from "./report";
