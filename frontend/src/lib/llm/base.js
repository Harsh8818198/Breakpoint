/**
 * Base LLM interface — defines the contract all LLM providers must implement.
 * This abstraction allows seamless switching between OpenAI and Gemini.
 */

export class BaseLLMProvider {
  constructor(apiKey, config = {}) {
    if (new.target === BaseLLMProvider) {
      throw new Error("BaseLLMProvider is abstract and cannot be instantiated directly");
    }
    this.apiKey = apiKey;
    this.config = config;
  }

  /**
   * Single-turn or multi-turn chat completion
   * @param {Array<{role: string, content: string}>} messages - Chat messages
   * @param {Object} options - { model, temperature, maxTokens, responseFormat }
   * @returns {Promise<{content: string, usage: {promptTokens: number, completionTokens: number}}>}
   */
  async chat(messages, options = {}) {
    throw new Error("chat() must be implemented by provider");
  }

  /**
   * Streaming chat completion
   * @param {Array<{role: string, content: string}>} messages
   * @param {Object} options
   * @returns {AsyncGenerator<string>} - Yields content chunks
   */
  async *chatStream(messages, options = {}) {
    throw new Error("chatStream() must be implemented by provider");
  }

  /**
   * Generate text embedding
   * @param {string} text - Text to embed
   * @returns {Promise<number[]>} - Embedding vector
   */
  async embedText(text) {
    throw new Error("embedText() must be implemented by provider");
  }

  /**
   * Generate an image from a text prompt
   * @param {string} prompt - Image description
   * @param {Object} options - { size, quality, style }
   * @returns {Promise<{url: string, base64: string}>}
   */
  async generateImage(prompt, options = {}) {
    throw new Error("generateImage() must be implemented by provider");
  }

  /**
   * Parse structured JSON from LLM response
   * @param {Array} messages
   * @param {Object} schema - Expected JSON structure description
   * @param {Object} options
   * @returns {Promise<Object>} - Parsed JSON object
   */
  async chatJSON(messages, schema = null, options = {}) {
    const response = await this.chat(messages, {
      ...options,
      responseFormat: "json",
    });

    try {
      // Try direct JSON parse
      let parsed = null;
      let rawContent = response.content.trim();

      // HEAL: If content is clearly truncated (ends with a partial key or value),
      // attempt to balance braces to make it valid JSON.
      const healJSON = (str) => {
        let stack = [];
        for (let i = 0; i < str.length; i++) {
          if (str[i] === '{' || str[i] === '[') stack.push(str[i]);
          else if (str[i] === '}') {
            if (stack[stack.length - 1] === '{') stack.pop();
          } else if (str[i] === ']') {
            if (stack[stack.length - 1] === '[') stack.pop();
          }
        }
        
        let healed = str;
        // Clean up partial trailing characters like "attr": "val
        healed = healed.replace(/,\s*["']?[a-zA-Z0-9_]*["']?:\s*["']?[^"']*$/, '');
        healed = healed.replace(/,\s*$/, '');

        while (stack.length > 0) {
          const last = stack.pop();
          healed += last === '{' ? '}' : ']';
        }
        return healed;
      };

      try {
        parsed = JSON.parse(rawContent);
      } catch {
        // Try extracting from code blocks
        const match = rawContent.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
        if (match) {
          try {
            parsed = JSON.parse(match[1].trim());
          } catch {
            parsed = JSON.parse(healJSON(match[1].trim()));
          }
        } else {
          // Try finding JSON object in text
          const jsonMatch = rawContent.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            try {
              parsed = JSON.parse(jsonMatch[0]);
            } catch {
              parsed = JSON.parse(healJSON(jsonMatch[0]));
            }
          }
        }
      }

      if (!parsed) {
        throw new Error("Could not extract JSON from LLM response");
      }

      return { data: parsed, usage: response.usage };
    } catch (error) {
      throw new Error(
        `Failed to parse JSON from LLM response: ${error.message}\nRaw response: ${response.content.substring(0, 500)}`
      );
    }
  }

  /**
   * Get provider name
   * @returns {string}
   */
  getProviderName() {
    throw new Error("getProviderName() must be implemented");
  }
}
