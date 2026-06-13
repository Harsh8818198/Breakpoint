import { errorResponse } from "@/lib/utils/apiResponse";
import { AppError } from "@/lib/utils/errors";

/**
 * Wraps an API route handler with standardized error handling.
 * Usage: export const GET = withErrorHandler(async (request) => { ... })
 */
export function withErrorHandler(handler) {
  return async function (request, context) {
    try {
      return await handler(request, context);
    } catch (error) {
      console.error(`[API Error] ${error.name}: ${error.message}`, {
        stack: error.stack,
        details: error.details,
      });

      if (error instanceof AppError) {
        return errorResponse(error.message, error.statusCode, error.details);
      }

      // Mongoose validation error
      if (error.name === "ValidationError" && error.errors) {
        const details = Object.keys(error.errors).map((key) => ({
          field: key,
          message: error.errors[key].message,
        }));
        return errorResponse("Validation failed", 422, details);
      }

      // Mongoose duplicate key error
      if (error.code === 11000) {
        const field = Object.keys(error.keyValue)[0];
        return errorResponse(
          `${field} already exists`,
          409,
          { field, value: error.keyValue[field] }
        );
      }

      // Mongoose cast error (invalid ObjectId etc)
      if (error.name === "CastError") {
        return errorResponse(`Invalid ${error.path}: ${error.value}`, 400);
      }

      // Generic server error
      return errorResponse(
        process.env.NODE_ENV === "development"
          ? error.message
          : "Internal server error",
        500
      );
    }
  };
}
