import { NextResponse } from "next/server";

/**
 * Standardized API response format for all Breakpoint endpoints
 */

export function successResponse(data, meta = {}, status = 200) {
  return NextResponse.json(
    {
      success: true,
      data,
      error: null,
      meta: {
        timestamp: new Date().toISOString(),
        ...meta,
      },
    },
    { status }
  );
}

export function errorResponse(message, status = 500, details = null) {
  return NextResponse.json(
    {
      success: false,
      data: null,
      error: {
        message,
        details,
        code: status,
      },
      meta: {
        timestamp: new Date().toISOString(),
      },
    },
    { status }
  );
}

export function validationErrorResponse(errors) {
  return NextResponse.json(
    {
      success: false,
      data: null,
      error: {
        message: "Validation failed",
        details: errors,
        code: 422,
      },
      meta: {
        timestamp: new Date().toISOString(),
      },
    },
    { status: 422 }
  );
}

export function paginatedResponse(data, page, limit, total) {
  return NextResponse.json(
    {
      success: true,
      data,
      error: null,
      meta: {
        timestamp: new Date().toISOString(),
        pagination: {
          page,
          limit,
          total,
          totalPages: Math.ceil(total / limit),
          hasNext: page * limit < total,
          hasPrev: page > 1,
        },
      },
    },
    { status: 200 }
  );
}
