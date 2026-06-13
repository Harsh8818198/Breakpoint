/**
 * Document extraction prompts — specialized for each document type
 */

export function getDocumentExtractionPrompt(documentType, content) {
  const typePrompts = {
    prd: `Extract from this Product Requirements Document:
- All features and their detailed specifications
- User stories and acceptance criteria
- Edge cases mentioned
- Technical constraints
- Pricing/tier information
- User roles and permissions
- Integration points`,

    api_spec: `Extract from this API Specification:
- All endpoints (URL, method, description)
- Authentication mechanisms
- Rate limiting rules
- Request/response schemas
- Error handling patterns
- Data models and relationships
- CORS and security headers`,

    db_schema: `Extract from this Database Schema:
- All tables/collections and their fields
- Relationships (foreign keys, references)
- Constraints (unique, not null, defaults)
- Indexes
- What's nullable (potential data integrity issues)
- What's unique (identity and dedup implications)`,

    wireframe: `Extract from this Wireframe/Mockup description:
- All visible UI elements and their functions
- User flow paths visible in the design
- Interactive elements (buttons, forms, modals)
- Navigation structure
- What data is shown to users
- What actions are available at each screen`,

    pricing: `Extract from this Pricing Documentation:
- All tiers and their limits
- What features are gated behind each tier
- Upgrade/downgrade mechanics
- Trial/free tier limitations
- What counts as usage (API calls, questions, etc.)
- Payment methods and billing cycle`,

    general: `Extract from this document all product-relevant information including:
- Features and capabilities
- User types and permissions
- Business rules and constraints
- Technical architecture details
- Data handling practices
- Security measures mentioned`,
  };

  return `You are a product analyst extracting structured information from a document.

DOCUMENT TYPE: ${documentType}
DOCUMENT CONTENT:
${content}

${typePrompts[documentType] || typePrompts.general}

Respond in JSON format:
{
  "documentType": "${documentType}",
  "extractedData": {
    "features": ["List of features found"],
    "userRoles": ["User types/roles mentioned"],
    "businessRules": ["Business rules, constraints, limits"],
    "technicalDetails": ["Technical implementation details"],
    "dataHandling": ["How data is stored, processed, shared"],
    "securityMeasures": ["Auth, encryption, access control details"],
    "pricingInfo": ["Tier details, limits, gates"],
    "edgeCases": ["Edge cases or undefined behaviors mentioned"],
    "gaps": ["Things NOT covered that should be addressed"]
  },
  "confidence": "high | medium | low",
  "notes": "Any important observations about the document"
}`;
}
