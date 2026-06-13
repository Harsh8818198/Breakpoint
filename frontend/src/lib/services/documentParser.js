import { put } from "@vercel/blob";
import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { getUserApiKey } from "@/lib/services/auth";
import { getDocumentExtractionPrompt } from "@/lib/prompts/intake/documentExtraction";
import connectDB from "@/lib/db/connect";
import Project from "@/lib/db/models/Project";
import { NotFoundError, ValidationError } from "@/lib/utils/errors";

/**
 * Detect document type from filename/mimetype
 */
function detectDocumentType(filename, mimeType) {
  const lower = filename.toLowerCase();

  if (lower.includes("prd") || lower.includes("requirement")) return "prd";
  if (lower.includes("swagger") || lower.includes("openapi") || lower.endsWith(".yaml") || lower.endsWith(".yml"))
    return "api_spec";
  if (lower.includes("schema") || lower.includes("database") || lower.includes("migration"))
    return "db_schema";
  if (lower.includes("wireframe") || lower.includes("mockup") || lower.includes("design"))
    return "wireframe";
  if (lower.includes("pricing") || lower.includes("plan") || lower.includes("tier"))
    return "pricing";

  return "general";
}

/**
 * Parse document content based on file type
 */
async function extractTextFromFile(buffer, mimeType, filename) {
  if (mimeType === "application/pdf") {
    const pdfParse = (await import("pdf-parse")).default;
    const data = await pdfParse(buffer);
    return data.text;
  }

  if (
    mimeType ===
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ) {
    const mammoth = await import("mammoth");
    const result = await mammoth.extractRawText({ buffer });
    return result.value;
  }

  if (mimeType === "application/json") {
    return buffer.toString("utf-8");
  }

  if (
    mimeType === "application/x-yaml" ||
    mimeType === "text/yaml" ||
    filename.endsWith(".yaml") ||
    filename.endsWith(".yml")
  ) {
    return buffer.toString("utf-8");
  }

  if (mimeType.startsWith("text/")) {
    return buffer.toString("utf-8");
  }

  throw new ValidationError(
    `Unsupported file type: ${mimeType}. Supported: PDF, DOCX, JSON, YAML, TXT`
  );
}

/**
 * Upload and store a document
 */
export async function uploadDocument(file, projectId, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  // Store in Vercel Blob
  const blob = await put(
    `breakpoint/${projectId}/${file.name}`,
    file,
    { access: "public" }
  );

  // Add to project's document list
  const docRecord = {
    filename: blob.pathname,
    originalName: file.name,
    mimeType: file.type,
    size: file.size,
    blobUrl: blob.url,
    parsedAt: null,
  };

  project.uploadedDocuments.push(docRecord);
  project.intakeMode = "document";
  await project.save();

  return docRecord;
}

/**
 * Parse all uploaded documents for a project
 */
export async function parseDocuments(projectId, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  if (!project.uploadedDocuments?.length) {
    throw new ValidationError("No documents uploaded yet");
  }

  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  const parsedResults = [];

  for (const doc of project.uploadedDocuments) {
    if (doc.parsedAt) continue; // Skip already parsed

    // Fetch document content from blob
    const response = await fetch(doc.blobUrl);
    const buffer = Buffer.from(await response.arrayBuffer());

    // Extract text
    const text = await extractTextFromFile(
      buffer,
      doc.mimeType,
      doc.originalName
    );

    // Detect document type
    const docType = detectDocumentType(doc.originalName, doc.mimeType);

    // Extract structured data via LLM
    const prompt = getDocumentExtractionPrompt(docType, text.slice(0, 15000));
    const result = await llm.chatJSON([{ role: "user", content: prompt }]);

    parsedResults.push({
      filename: doc.originalName,
      documentType: docType,
      ...result.data,
    });

    // Mark as parsed
    doc.parsedAt = new Date();
  }

  await project.save();

  return parsedResults;
}
