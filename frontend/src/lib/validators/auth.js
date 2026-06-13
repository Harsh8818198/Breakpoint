import { z } from "zod";

export const registerSchema = z.object({
  email: z
    .string()
    .email("Invalid email address")
    .max(255, "Email too long"),
  password: z
    .string()
    .min(6, "Password must be at least 6 characters")
    .max(128, "Password too long"),
  name: z
    .string()
    .min(2, "Name must be at least 2 characters")
    .max(100, "Name too long")
    .trim(),
});

export const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

export const updateSettingsSchema = z.object({
  defaultLlmProvider: z.enum(["openai", "gemini"]).optional(),
  openaiApiKey: z.string().optional().nullable(),
  geminiApiKey: z.string().optional().nullable(),
});

export const updateProfileSchema = z.object({
  name: z
    .string()
    .min(2, "Name must be at least 2 characters")
    .max(100, "Name too long")
    .trim()
    .optional(),
  avatar: z.string().url("Invalid avatar URL").optional().nullable(),
});
