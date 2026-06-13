import { Octokit } from "@octokit/rest";
import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { getUserApiKey } from "@/lib/services/auth";
import connectDB from "@/lib/db/connect";
import Project from "@/lib/db/models/Project";
import { NotFoundError, ValidationError, AppError } from "@/lib/utils/errors";

/**
 * File patterns to analyze for product understanding
 */
const ANALYSIS_PATTERNS = {
  routes: [
    "routes/**", "src/routes/**", "src/app/api/**", "pages/api/**",
    "app/api/**", "controllers/**", "src/controllers/**",
  ],
  models: [
    "models/**", "src/models/**", "prisma/schema.prisma",
    "src/db/**", "database/**", "schemas/**",
  ],
  middleware: [
    "middleware/**", "src/middleware/**", "src/lib/middleware/**",
  ],
  auth: [
    "**/auth/**", "**/authentication/**", "**/passport*",
  ],
  config: [
    ".env.example", "config/**", "src/config/**",
    "next.config.*", "nuxt.config.*", "vite.config.*",
  ],
  payment: [
    "**/payment/**", "**/billing/**", "**/stripe/**", "**/razorpay/**",
    "**/subscription/**",
  ],
};

/**
 * Connect to a GitHub repository
 */
export async function connectRepo(repoUrl, accessToken, projectId, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  // Parse GitHub URL
  const { owner, repo } = parseGitHubUrl(repoUrl);

  // Verify access
  const octokit = new Octokit({ auth: accessToken });
  
  try {
    const { data } = await octokit.repos.get({ owner, repo });
    
    project.intakeMode = "codebase";
    project.codebaseConfig = {
      repoUrl,
      branch: data.default_branch,
      lastAnalyzedAt: null,
    };
    await project.save();

    return {
      name: data.full_name,
      description: data.description,
      defaultBranch: data.default_branch,
      language: data.language,
      isPrivate: data.private,
      connected: true,
    };
  } catch (error) {
    throw new AppError(
      `Failed to connect to repository: ${error.message}`,
      400
    );
  }
}

/**
 * Analyze a connected codebase
 */
export async function analyzeCodebase(projectId, accessToken, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  if (!project.codebaseConfig?.repoUrl) {
    throw new ValidationError("No repository connected. Connect a repo first.");
  }

  const { owner, repo } = parseGitHubUrl(project.codebaseConfig.repoUrl);
  const octokit = new Octokit({ auth: accessToken });

  // Get repo tree
  const { data: tree } = await octokit.git.getTree({
    owner,
    repo,
    tree_sha: project.codebaseConfig.branch || "main",
    recursive: "true",
  });

  // Categorize files
  const categorizedFiles = categorizeFiles(tree.tree);

  // Read key files (limit to prevent huge payloads)
  const fileContents = {};
  const filesToRead = selectKeyFiles(categorizedFiles, 30);

  for (const file of filesToRead) {
    try {
      const { data } = await octokit.repos.getContent({
        owner,
        repo,
        path: file.path,
      });
      if (data.type === "file" && data.size < 50000) {
        fileContents[file.path] = {
          content: Buffer.from(data.content, "base64").toString("utf-8"),
          category: file.category,
        };
      }
    } catch {
      // Skip files that can't be read
    }
  }

  // Analyze with LLM
  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  const analysisPrompt = getCodebaseAnalysisPrompt(fileContents, categorizedFiles);
  const result = await llm.chatJSON([{ role: "user", content: analysisPrompt }]);

  // Update project
  project.codebaseConfig.lastAnalyzedAt = new Date();
  await project.save();

  return {
    analysis: result.data,
    filesAnalyzed: Object.keys(fileContents).length,
    totalFiles: tree.tree.filter((t) => t.type === "blob").length,
    categories: Object.fromEntries(
      Object.entries(categorizedFiles).map(([k, v]) => [k, v.length])
    ),
  };
}

/**
 * Analyze a live product URL
 */
export async function analyzeLiveProduct(url, projectId, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  // Fetch the main page and parse
  const response = await fetch(url, {
    headers: {
      "User-Agent":
        "Breakpoint-Analyzer/1.0 (Product Security Analysis Tool)",
    },
  });

  const html = await response.text();
  const headers = Object.fromEntries(response.headers.entries());

  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  const analysisPrompt = `Analyze this live product page for product understanding and security assessment.

URL: ${url}
RESPONSE HEADERS: ${JSON.stringify(headers, null, 2)}
HTML CONTENT (first 10000 chars): ${html.slice(0, 10000)}

Extract in JSON format:
{
  "productOverview": "What this product appears to be",
  "features": ["Visible features from the UI"],
  "userFlows": ["Apparent user journeys"],
  "authMechanism": "How users log in",
  "securityHeaders": {
    "present": ["Security headers found"],
    "missing": ["Important security headers NOT found"]
  },
  "clientSideExposures": ["Things that might be exposed client-side"],
  "apiEndpoints": ["Any API URLs found in the HTML/JS"],
  "thirdPartyServices": ["Third-party integrations detected"]
}`;

  const result = await llm.chatJSON([{ role: "user", content: analysisPrompt }]);

  return result.data;
}

// ─── Helper Functions ───

function parseGitHubUrl(url) {
  const match = url.match(
    /github\.com[/:]([^/]+)\/([^/.]+)/
  );
  if (!match) throw new ValidationError("Invalid GitHub URL");
  return { owner: match[1], repo: match[2] };
}

function categorizeFiles(treeNodes) {
  const categories = {};
  for (const [category, patterns] of Object.entries(ANALYSIS_PATTERNS)) {
    categories[category] = treeNodes.filter((node) => {
      if (node.type !== "blob") return false;
      return patterns.some((pattern) => {
        const regex = new RegExp(
          "^" + pattern.replace(/\*\*/g, ".*").replace(/\*/g, "[^/]*") + "$"
        );
        return regex.test(node.path);
      });
    });
  }
  return categories;
}

function selectKeyFiles(categorizedFiles, maxFiles) {
  const selected = [];
  const priorities = ["routes", "models", "auth", "middleware", "payment", "config"];

  for (const category of priorities) {
    const files = categorizedFiles[category] || [];
    for (const file of files) {
      if (selected.length >= maxFiles) break;
      selected.push({ ...file, category });
    }
  }

  return selected;
}

function getCodebaseAnalysisPrompt(fileContents, categories) {
  const fileList = Object.entries(fileContents)
    .map(([path, data]) => `\n--- FILE: ${path} (${data.category}) ---\n${data.content.slice(0, 3000)}`)
    .join("\n");

  return `You are an expert product security analyst analyzing a codebase for product understanding.

FILES ANALYZED:
${fileList}

FILE CATEGORIES FOUND:
${JSON.stringify(Object.fromEntries(Object.entries(categories).map(([k, v]) => [k, v.map((f) => f.path)])), null, 2)}

Extract comprehensive product understanding in JSON format:
{
  "routes": [{"path": "/api/...", "method": "GET/POST", "description": "What it does", "authRequired": true/false, "rateLimit": "if found"}],
  "dataModels": [{"name": "Model name", "fields": ["key fields"], "relationships": ["related models"], "sensitiveFields": ["fields with PII/secrets"]}],
  "authSystem": {"type": "JWT/session/OAuth", "providers": ["Google", "email"], "tokenStorage": "cookie/localStorage", "roleBasedAccess": true/false},
  "paymentIntegration": {"provider": "Stripe/Razorpay/none", "tiers": ["tier names"], "gatedFeatures": ["features behind paywall"]},
  "securityFindings": [{"issue": "description", "severity": "critical/high/medium/low", "file": "filename"}],
  "fileUploadHandling": {"present": true/false, "sizeLimit": "if found", "typeValidation": "how checked"},
  "rateLimiting": {"present": true/false, "rules": ["rate limit rules found"]},
  "environmentVariables": ["env vars referenced"],
  "featureFlags": ["any feature toggles found"],
  "thirdPartyDependencies": ["key dependencies"],
  "overallArchitecture": "Brief description of the tech stack and architecture"
}`;
}
