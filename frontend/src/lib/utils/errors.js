/**
 * Custom error classes for Breakpoint
 */

export class AppError extends Error {
  constructor(message, statusCode = 500, details = null) {
    super(message);
    this.name = "AppError";
    this.statusCode = statusCode;
    this.details = details;
  }
}

export class ValidationError extends AppError {
  constructor(message = "Validation failed", details = null) {
    super(message, 422, details);
    this.name = "ValidationError";
  }
}

export class AuthError extends AppError {
  constructor(message = "Authentication required") {
    super(message, 401);
    this.name = "AuthError";
  }
}

export class ForbiddenError extends AppError {
  constructor(message = "Access denied") {
    super(message, 403);
    this.name = "ForbiddenError";
  }
}

export class NotFoundError extends AppError {
  constructor(resource = "Resource") {
    super(`${resource} not found`, 404);
    this.name = "NotFoundError";
  }
}

export class ConflictError extends AppError {
  constructor(message = "Resource already exists") {
    super(message, 409);
    this.name = "ConflictError";
  }
}

export class LLMError extends AppError {
  constructor(provider, message, details = null) {
    super(`LLM Error (${provider}): ${message}`, 502, details);
    this.name = "LLMError";
    this.provider = provider;
  }
}

export class RateLimitError extends AppError {
  constructor(message = "Too many requests. Please try again later.") {
    super(message, 429);
    this.name = "RateLimitError";
  }
}

export class BlueprintLockedError extends AppError {
  constructor() {
    super("Blueprint is locked and cannot be modified during simulation", 423);
    this.name = "BlueprintLockedError";
  }
}

export class SimulationError extends AppError {
  constructor(message, details = null) {
    super(`Simulation Error: ${message}`, 500, details);
    this.name = "SimulationError";
  }
}
