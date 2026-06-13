import { GoogleGenerativeAI } from "@google/generative-ai";
import { BaseLLMProvider } from "./base.js";
import { LLMError } from "@/lib/utils/errors";
import { DEFAULT_LLM_SETTINGS } from "@/lib/config/defaults";
import { retryWithBackoff } from "@/lib/utils/helpers";

/**
 * Google Gemini/Gemma LLM Provider adapter.
 * Handles both Gemini (supports native JSON mode) and Gemma (requires prompt-based JSON).
 */
export class GeminiProvider extends BaseLLMProvider {
  constructor(apiKey, config = {}) {
    super(apiKey, config);
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.defaults = DEFAULT_LLM_SETTINGS.gemini;
  }

  getProviderName() {
    return "gemini";
  }

  /**
   * Check if the model is a Gemma model (vs Gemini).
   * Gemma models do NOT support responseMimeType JSON mode.
   */
  _isGemmaModel(modelName) {
    return modelName?.toLowerCase().startsWith("gemma");
  }

  /**
   * Extract text from a Gemini/Gemma response, filtering out "thought" parts.
   * Gemma models can return multi-part responses where some parts are internal
   * reasoning (thought: true) and others are the actual output.
   */
  _extractText(response) {
    const candidates = response.candidates;
    if (!candidates || candidates.length === 0) {
      return "";
    }

    const parts = candidates[0]?.content?.parts || [];

    // Filter out thought parts and concatenate the actual output text
    const outputParts = parts.filter((p) => !p.thought && p.text);

    if (outputParts.length > 0) {
      return outputParts.map((p) => p.text).join("");
    }

    // Fallback: try the standard .text() method
    try {
      return response.text();
    } catch {
      return "";
    }
  }

  /**
   * Convert OpenAI-style messages to Gemini format.
   * Gemini API requires: (1) first history entry must be role "user",
   * (2) roles must alternate user/model. We handle conversations that
   * start with an assistant greeting by folding it into systemInstruction,
   * and merge consecutive same-role messages to maintain alternation.
   */
  _convertMessages(messages) {
    let systemParts = messages
      .filter((m) => m.role === "system")
      .map((m) => m.content);

    const nonSystemMessages = messages.filter((m) => m.role !== "system");

    // If conversation starts with assistant message(s), fold them into
    // the system instruction so history can start with "user".
    let startIdx = 0;
    while (
      startIdx < nonSystemMessages.length &&
      nonSystemMessages[startIdx].role === "assistant"
    ) {
      systemParts.push(nonSystemMessages[startIdx].content);
      startIdx++;
    }

    const remaining = nonSystemMessages.slice(startIdx);

    // Build history (all but the last message), merging consecutive same-role entries
    const rawHistory = [];
    for (let i = 0; i < remaining.length - 1; i++) {
      const geminiRole = remaining[i].role === "assistant" ? "model" : "user";
      const last = rawHistory[rawHistory.length - 1];
      if (last && last.role === geminiRole) {
        // Merge consecutive same-role messages
        last.parts[0].text += "\n\n" + remaining[i].content;
      } else {
        rawHistory.push({
          role: geminiRole,
          parts: [{ text: remaining[i].content }],
        });
      }
    }

    const lastMessage = remaining.length > 0
      ? remaining[remaining.length - 1]
      : null;

    return {
      systemInstruction: systemParts.length > 0 ? systemParts.join("\n\n") : undefined,
      history: rawHistory,
      userMessage: lastMessage?.content || "",
    };
  }

  async chat(messages, options = {}) {
    const model = options.model || this.defaults.chatModel;
    const temperature = options.temperature ?? this.defaults.temperature;
    const maxTokens = options.maxTokens || this.defaults.maxTokens;
    const isGemma = this._isGemmaModel(model);

    try {
      const { systemInstruction, history, userMessage } =
        this._convertMessages(messages);

      // Build generation config
      const generationConfig = {
        temperature,
        maxOutputTokens: maxTokens,
      };

      // Only set responseMimeType for Gemini models (not Gemma)
      if (!isGemma && options.responseFormat === "json") {
        generationConfig.responseMimeType = "application/json";
      }

      const generativeModel = this.genAI.getGenerativeModel({
        model,
        systemInstruction,
        generationConfig,
      });

      const chat = generativeModel.startChat({ history });

      const result = await retryWithBackoff(
        () => chat.sendMessage(userMessage),
        2,
        1000
      );

      const response = result.response;
      const text = this._extractText(response);
      const usage = response.usageMetadata;

      return {
        content: text,
        usage: {
          promptTokens: usage?.promptTokenCount || 0,
          completionTokens: usage?.candidatesTokenCount || 0,
        },
      };
    } catch (error) {
      throw new LLMError(
        "gemini",
        error.message,
        { model, errorCode: error.code }
      );
    }
  }

  async *chatStream(messages, options = {}) {
    const model = options.model || this.defaults.chatModel;
    const temperature = options.temperature ?? this.defaults.temperature;
    const maxTokens = options.maxTokens || this.defaults.maxTokens;

    try {
      const { systemInstruction, history, userMessage } =
        this._convertMessages(messages);

      const generativeModel = this.genAI.getGenerativeModel({
        model,
        systemInstruction,
        generationConfig: {
          temperature,
          maxOutputTokens: maxTokens,
        },
      });

      const chat = generativeModel.startChat({ history });
      const result = await chat.sendMessageStream(userMessage);

      for await (const chunk of result.stream) {
        // For streaming, filter out thought chunks
        const candidates = chunk.candidates;
        if (candidates && candidates[0]?.content?.parts) {
          const outputParts = candidates[0].content.parts.filter(
            (p) => !p.thought && p.text
          );
          for (const part of outputParts) {
            yield part.text;
          }
        } else {
          const text = chunk.text();
          if (text) {
            yield text;
          }
        }
      }
    } catch (error) {
      throw new LLMError("gemini", error.message, { model });
    }
  }

  async embedText(text) {
    try {
      const model = this.genAI.getGenerativeModel({
        model: this.defaults.embeddingModel,
      });

      const result = await retryWithBackoff(
        () => model.embedContent(text),
        2,
        1000
      );

      return result.embedding.values;
    } catch (error) {
      throw new LLMError("gemini", `Embedding error: ${error.message}`);
    }
  }

  async generateImage(prompt, options = {}) {
    try {
      // Gemini Imagen API via REST endpoint (SDK support is evolving)
      const response = await retryWithBackoff(async () => {
        const res = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/${this.defaults.imageModel}:predict?key=${this.apiKey}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              instances: [{ prompt }],
              parameters: {
                sampleCount: 1,
                aspectRatio: options.aspectRatio || "1:1",
                personGeneration: "dont_allow",
              },
            }),
          }
        );

        if (!res.ok) {
          const error = await res.json();
          throw new Error(error.error?.message || `HTTP ${res.status}`);
        }

        return res.json();
      }, 2, 2000);

      const imageBytes = response.predictions?.[0]?.bytesBase64Encoded;
      
      if (!imageBytes) {
        throw new Error("No image returned from Gemini Imagen");
      }

      return {
        base64: imageBytes,
        url: `data:image/png;base64,${imageBytes}`,
      };
    } catch (error) {
      throw new LLMError("gemini", `Image generation error: ${error.message}`);
    }
  }
}
