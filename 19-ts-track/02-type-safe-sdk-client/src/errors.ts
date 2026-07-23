/**
 * The typed error hierarchy every SDK method must reject with. A caller
 * catching an error from this package should never see a bare `Error`, and
 * never see a `ZodError` leak past the request boundary unwrapped -- wrap
 * it in `SdkValidationError` instead, so callers can `instanceof`-narrow on
 * SDK-defined classes without knowing zod is involved at all.
 */

import type { ZodError } from "zod";
import type { ApiErrorBody } from "./schemas";

/** Common base so callers can catch `SdkError` to mean "anything this SDK throws". */
export abstract class SdkError extends Error {
  abstract readonly kind: string;
}

/**
 * A 2xx response's JSON body did not match the schema it was validated
 * against (e.g. the `/products/malformed` and `/products/wrongshape`
 * routes). `zodError` carries the original `ZodError` for callers that want
 * the field-level detail; it must never be thrown on its own in its place.
 */
export class SdkValidationError extends SdkError {
  readonly kind = "validation" as const;

  constructor(
    public readonly path: string,
    public readonly zodError: ZodError,
  ) {
    super(`response from ${path} failed schema validation: ${zodError.message}`);
    this.name = "SdkValidationError";
  }
}

/** A single-resource GET (e.g. `getProduct`) returned 404. */
export class ApiNotFoundError extends SdkError {
  readonly kind = "not_found" as const;

  constructor(public readonly path: string) {
    super(`not found: ${path}`);
    this.name = "ApiNotFoundError";
  }
}

/**
 * A request that required authentication returned 401 -- either no/invalid
 * credentials were presented (`login`), or the access token was rejected
 * and, for `me()`, the single refresh-and-retry also failed.
 */
export class ApiAuthError extends SdkError {
  readonly kind = "auth" as const;

  constructor(public readonly path: string) {
    super(`unauthorized: ${path}`);
    this.name = "ApiAuthError";
  }
}

/** Any other non-2xx response, carrying the parsed `ApiErrorBody` envelope. */
export class ApiRequestError extends SdkError {
  readonly kind = "api_error" as const;

  constructor(
    public readonly status: number,
    public readonly path: string,
    public readonly body: ApiErrorBody,
  ) {
    super(`request to ${path} failed with status ${status}`);
    this.name = "ApiRequestError";
  }
}
