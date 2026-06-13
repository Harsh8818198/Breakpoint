import OpenAI from "openai";
import { BaseLLMProvider } from "./base.js";
import { LLMError } from "@/lib/utils/errors";
import { DEFAULT_LLM_SETTINGS } from "@/lib/config/defaults";
import { retryWithBackoff } from "@/lib/utils/helpers";

/**
 * OpenAI LLM Provider adapter
 */
export class OpenAIProvider extends BaseLLMProvider {
  constructor(apiKey, config = {}) {
    super(apiKey, config);
    this.client = new OpenAI({ apiKey });
    this.defaults = DEFAULT_LLM_SETTINGS.openai;
  }

  getProviderName() {
    return "openai";
  }

  async chat(messages, options = {}) {
    const model = options.model || this.defaults.chatModel;
    const temperature = options.temperature ?? this.defaults.temperature;
    const maxTokens = options.maxTokens || this.defaults.maxTokens;

    try {
      const requestBody = {
        model,
        messages: messages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        temperature,
        max_tokens: maxTokens,
      };

      if (options.responseFormat === "json") {
        requestBody.response_format = { type: "json_object" };
      }

      const response = await retryWithBackoff(
        () => this.client.chat.completions.create(requestBody),
        2,
        1000
      );

      return {
        content: response.choices[0].message.content,
        usage: {
          promptTokens: response.usage?.prompt_tokens || 0,
          completionTokens: response.usage?.completion_tokens || 0,
        },
      };
    } catch (error) {
      throw new LLMError(
        "openai",
        error.message,
        { model, statusCode: error.status }
      );
    }
  }

  async *chatStream(messages, options = {}) {
    const model = options.model || this.defaults.chatModel;
    const temperature = options.temperature ?? this.defaults.temperature;
    const maxTokens = options.maxTokens || this.defaults.maxTokens;

    try {
      const stream = await this.client.chat.completions.create({
        model,
        messages: messages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        temperature,
        max_tokens: maxTokens,
        stream: true,
      });

      for await (const chunk of stream) {
        const content = chunk.choices[0]?.delta?.content;
        if (content) {
          yield content;
        }
      }
    } catch (error) {
      throw new LLMError("openai", error.message, { model });
    }
  }

  async embedText(text) {
    try {
      const response = await retryWithBackoff(
        () =>
          this.client.embeddings.create({
            model: this.defaults.embeddingModel,
            input: text,
          }),
        2,
        1000
      );

      return response.data[0].embedding;
    } catch (error) {
      throw new LLMError("openai", `Embedding error: ${error.message}`);
    }
  }

  async generateImage(prompt, options = {}) {
    try {
      const response = await retryWithBackoff(
        () =>
          this.client.images.generate({
            model: options.model || this.defaults.imageModel,
            prompt,
            n: 1,
            size: options.size || "1024x1024",
            quality: options.quality || "standard",
            response_format: "url",
          }),
        2,
        2000
      );

      return {
        url: response.data[0].url,
        revisedPrompt: response.data[0].revised_prompt,
      };
    } catch (error) {
      throw new LLMError("openai", `Image generation error: ${error.message}`);
    }
  }
}
