import { RateLimitError } from "@/lib/utils/errors";
import { errorResponse } from "@/lib/utils/apiResponse";

/**
 * Simple in-memory rate limiter for development.
 * In production, use Redis or Upstash rate limiting.
 */
const rateLimitStore = new Map();

const WINDOW_MS = parseInt(process.env.RATE_LIMIT_WINDOW_MS || "60000");
const MAX_REQUESTS = parseInt(process.env.RATE_LIMIT_MAX || "100");

function cleanupExpired() {
  const now = Date.now();
  for (const [key, entry] of rateLimitStore) {
    if (now - entry.start > WINDOW_MS) {
      rateLimitStore.delete(key);
    }
  }
}

export function withRateLimit(handler, options = {}) {
  const maxRequests = options.max || MAX_REQUESTS;
  const windowMs = options.windowMs || WINDOW_MS;

  return async function (request, context) {
    // Clean up periodically
    if (Math.random() < 0.1) cleanupExpired();

    // Get identifier (IP or user ID)
    const identifier =
      request.userId ||
      request.headers.get("x-forwarded-for") ||
      request.headers.get("x-real-ip") ||
      "anonymous";

    const key = `${identifier}:${request.url}`;
    const now = Date.now();

    let entry = rateLimitStore.get(key);
    if (!entry || now - entry.start > windowMs) {
      entry = { count: 0, start: now };
      rateLimitStore.set(key, entry);
    }

    entry.count++;

    if (entry.count > maxRequests) {
      return errorResponse(
        "Too many requests. Please try again later.",
        429,
        {
          retryAfter: Math.ceil((windowMs - (now - entry.start)) / 1000),
        }
      );
    }

    return handler(request, context);
  };
}
