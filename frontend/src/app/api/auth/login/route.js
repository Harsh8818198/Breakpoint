import { successResponse } from "@/lib/utils/apiResponse";

/**
 * Mocked login endpoint to support passwordless dev mode
 */
export async function POST(request) {
  return successResponse({
    user: {
      email: "dev@breakpoint.local",
      name: "Developer",
    },
    token: "dev-bypass-token",
  });
}
