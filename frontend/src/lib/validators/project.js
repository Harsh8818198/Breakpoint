import { z } from "zod";

export const createProjectSchema = z.object({
  name: z
    .string()
    .min(1, "Project name is required")
    .max(200, "Name too long")
    .trim(),
  description: z.string().max(2000, "Description too long").optional().default(""),
  llmProvider: z.enum(["openai", "gemini"]).optional().default("gemini"),
  intakeMode: z
    .enum(["conversation", "document", "codebase"])
    .optional()
    .default("conversation"),
});

export const updateProjectSchema = z.object({
  name: z.string().min(1).max(200).trim().optional(),
  description: z.string().max(2000).optional(),
  llmProvider: z.enum(["openai", "gemini"]).optional(),
});
