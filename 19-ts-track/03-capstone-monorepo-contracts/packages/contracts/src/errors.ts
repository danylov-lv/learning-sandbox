// @t3/contracts — the shared error DTO.
//
// Every non-2xx response the marketplace API returns is this exact shape.
// @t3/api parses it and throws a typed error carrying it; nothing
// downstream should ever need to guess an error body's shape by hand.

import { z } from "zod";

/**
 *   { error: { code: string; message: string } }
 */
export const ApiErrorSchema = z.unknown();
export type ApiError = z.infer<typeof ApiErrorSchema>;
