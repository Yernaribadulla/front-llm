import { useEffect, useRef, useState } from "react";
import "./App.css";

type Model = {
  id: string;
};

type TextContent = {
  type: "text";
  text: string;
};

type ImageContent = {
  type: "image_url";
  image_url: {
    url: string;
  };
};

type MessageContent =
  | string
  | (TextContent | ImageContent)[];

type Message = {
  role: "user" | "assistant";
  content: MessageContent;
};

const API_URL = "";

function getSessionId(): string {
  let sessionId = sessionStorage.getItem("llm_session_id");

  if (!sessionId) {
    sessionId = crypto.randomUUID();

    sessionStorage.setItem(
      "llm_session_id",
      sessionId
    );
  }

  return sessionId;
}

function App() {
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] =
    useState("");

  const [lmStudioAvailable, setLmStudioAvailable] =
    useState(false);

  const [messages, setMessages] = useState<Message[]>(
    []
  );

  const [input, setInput] = useState("");

  const [selectedImage, setSelectedImage] =
    useState<string | null>(null);

  const [isGenerating, setIsGenerating] =
    useState(false);

  const [error, setError] = useState("");

  const abortControllerRef =
    useRef<AbortController | null>(null);

  const chatRef =
    useRef<HTMLElement | null>(null);

  const shouldAutoScrollRef =
    useRef(true);

  // ==========================================================
  // MODELS
  // ==========================================================

  async function loadModels() {
    try {
      const response = await fetch(
        `${API_URL}/api/models`
      );

      if (!response.ok) {
        throw new Error(
          "Не удалось получить список моделей."
        );
      }

      const data = await response.json();

      setModels(data.models);
      setLmStudioAvailable(
        data.lm_studio_available
      );

      if (data.models.length > 0) {
        setSelectedModel(
          currentModel =>
            currentModel || data.models[0].id
        );
      }
    } catch (error) {
      console.error(
        "Failed to load models:",
        error
      );

      setLmStudioAvailable(false);
      setModels([]);
    }
  }

  useEffect(() => {
    loadModels();
  }, []);

  // ==========================================================
  // AUTO SCROLL
  // ==========================================================

  function handleChatScroll() {
    const chat = chatRef.current;

    if (!chat) {
      return;
    }

    const distanceFromBottom =
      chat.scrollHeight -
      chat.scrollTop -
      chat.clientHeight;

    shouldAutoScrollRef.current =
      distanceFromBottom < 100;
  }

  function scrollToBottom(force = false) {
    const chat = chatRef.current;

    if (!chat) {
      return;
    }

    if (
      !force &&
      !shouldAutoScrollRef.current
    ) {
      return;
    }

    requestAnimationFrame(() => {
      chat.scrollTo({
        top: chat.scrollHeight,
        behavior: force ? "smooth" : "auto",
      });
    });
  }

  useEffect(() => {
    if (messages.length === 0) {
      return;
    }

    scrollToBottom();
  }, [messages]);

  // ==========================================================
  // IMAGE
  // ==========================================================

  async function handleImageChange(
    event: React.ChangeEvent<HTMLInputElement>
  ) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    event.target.value = "";

    if (!file.type.startsWith("image/")) {
      setError(
        "Можно выбрать только изображение."
      );
      return;
    }

    setError("");

    let objectUrl = "";

    try {
      const image = new Image();

      objectUrl = URL.createObjectURL(file);

      image.src = objectUrl;

      await new Promise<void>(
        (resolve, reject) => {
          image.onload = () => resolve();

          image.onerror = () =>
            reject(
              new Error(
                "Браузер не смог открыть изображение."
              )
            );
        }
      );

      const MAX_SIZE = 1536;

      let width = image.naturalWidth;
      let height = image.naturalHeight;

      if (
        width > MAX_SIZE ||
        height > MAX_SIZE
      ) {
        const scale = Math.min(
          MAX_SIZE / width,
          MAX_SIZE / height
        );

        width = Math.round(width * scale);
        height = Math.round(height * scale);
      }

      const canvas =
        document.createElement("canvas");

      canvas.width = width;
      canvas.height = height;

      const context =
        canvas.getContext("2d");

      if (!context) {
        throw new Error(
          "Не удалось создать Canvas."
        );
      }

      context.drawImage(
        image,
        0,
        0,
        width,
        height
      );

      const dataUrl =
        canvas.toDataURL(
          "image/jpeg",
          0.85
        );

      if (
        !dataUrl.startsWith(
          "data:image/jpeg;base64,"
        )
      ) {
        throw new Error(
          "Не удалось получить Base64 JPEG."
        );
      }

      const commaIndex =
        dataUrl.indexOf(",");

      if (commaIndex === -1) {
        throw new Error(
          "Некорректный Data URL."
        );
      }

      const base64Part =
        dataUrl.slice(
          commaIndex + 1
        );

      if (
        !base64Part ||
        base64Part.length < 100
      ) {
        throw new Error(
          "Получено пустое изображение."
        );
      }

      console.log("IMAGE READY");
      console.log("TYPE:", "image/jpeg");
      console.log(
        "SIZE:",
        `${width}x${height}`
      );
      console.log(
        "BASE64 LENGTH:",
        base64Part.length
      );
      console.log(
        "PREFIX:",
        dataUrl.substring(0, 30)
      );

      setSelectedImage(dataUrl);
    } catch (error) {
      console.error(
        "IMAGE ERROR:",
        error
      );

      setSelectedImage(null);

      setError(
        error instanceof Error
          ? error.message
          : "Не удалось обработать изображение."
      );
    } finally {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    }
  }

  function removeImage() {
    setSelectedImage(null);
  }

  // ==========================================================
  // SEND MESSAGE
  // ==========================================================

  async function sendMessage() {
    const text = input.trim();

    if (
      (!text && !selectedImage) ||
      isGenerating ||
      !selectedModel
    ) {
      return;
    }

    setError("");

    // ========================================================
    // CONTENT
    // ========================================================

    const userContent:
      (TextContent | ImageContent)[] = [];

    if (text) {
      userContent.push({
        type: "text",
        text,
      });
    }

    if (selectedImage) {
      if (
        !selectedImage.startsWith(
          "data:image/"
        )
      ) {
        setError(
          "Изображение имеет неправильный формат."
        );
        return;
      }

      if (
        !selectedImage.includes(
          ";base64,"
        )
      ) {
        setError(
          "Изображение не содержит Base64."
        );
        return;
      }

      userContent.push({
        type: "image_url",
        image_url: {
          url: selectedImage,
        },
      });
    }

    const userMessage: Message = {
      role: "user",
      content: userContent,
    };

    const newMessages: Message[] = [
      ...messages,
      userMessage,
    ];

    shouldAutoScrollRef.current = true;

    setInput("");
    setSelectedImage(null);

    // Добавляем сообщение пользователя
    // и пустое сообщение ассистента.
    setMessages([
      ...newMessages,
      {
        role: "assistant",
        content: "",
      },
    ]);

    setIsGenerating(true);

    const controller =
      new AbortController();

    abortControllerRef.current =
      controller;

    try {
      // ======================================================
      // DEBUG REQUEST
      // ======================================================

      console.log(
        "SENDING MESSAGE:"
      );

      console.log(
        JSON.stringify(
          {
            model: selectedModel,
            messages: newMessages,
            session_id: getSessionId(),
          },
          null,
          2
        ).replace(
          /data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/g,
          "data:image/jpeg;base64,...[HIDDEN]"
        )
      );

      // ======================================================
      // REQUEST
      // ======================================================

      const response = await fetch(
        `${API_URL}/api/chat`,
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({
            model: selectedModel,

            messages: newMessages,

            session_id: getSessionId(),

            params: {
              temperature: 0.7,
              max_tokens: 1024,
              top_p: 1.0,
            },
          }),

          signal: controller.signal,
        }
      );

      if (
        !response.ok ||
        !response.body
      ) {
        let message =
          "Не удалось подключиться к backend";

        try {
          const data =
            await response.json();

          if (data.detail) {
            message =
              typeof data.detail === "string"
                ? data.detail
                : JSON.stringify(
                    data.detail
                  );
          }
        } catch {
          // Ignore JSON parsing error.
        }

        throw new Error(message);
      }

      // ======================================================
      // SSE STREAM
      // ======================================================

      const reader =
        response.body.getReader();

      const decoder =
        new TextDecoder();

      let buffer = "";

      while (true) {
        const {
          value,
          done,
        } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(
          value,
          {
            stream: true,
          }
        );

        const events =
          buffer.split("\n\n");

        buffer =
          events.pop() || "";

        for (
          const event of events
        ) {
          const lines =
            event.split("\n");

          let eventType = "";
          let data = "";

          for (
            const line of lines
          ) {
            if (
              line.startsWith(
                "event: "
              )
            ) {
              eventType =
                line.slice(7);
            }

            if (
              line.startsWith(
                "data: "
              )
            ) {
              data =
                line.slice(6);
            }
          }

          if (!data) {
            continue;
          }

          let parsed: {
            content?: string;
            message?: string;
            code?: string;
          };

          try {
            parsed =
              JSON.parse(data);
          } catch (error) {
            console.error(
              "Invalid SSE JSON:",
              error
            );
            continue;
          }

          // ==================================================
          // TOKEN
          // ==================================================

          if (
            eventType === "token"
          ) {
            const token =
              parsed.content || "";

            setMessages(
              current => {
                const updated =
                  [...current];

                const last =
                  updated.length - 1;

                if (last < 0) {
                  return current;
                }

                const currentContent =
                  updated[last].content;

                updated[last] = {
                  ...updated[last],

                  content:
                    typeof currentContent ===
                    "string"
                      ? currentContent + token
                      : token,
                };

                return updated;
              }
            );
          }

          // ==================================================
          // ERROR
          // ==================================================

          if (
            eventType === "error"
          ) {
            setError(
              parsed.message ||
                "Произошла ошибка."
            );
          }

          // ==================================================
          // DONE
          // ==================================================

          if (
            eventType === "done"
          ) {
            setIsGenerating(false);
          }
        }
      }
    } catch (err) {
      if (
        err instanceof DOMException &&
        err.name === "AbortError"
      ) {
        return;
      }

      setError(
        err instanceof Error
          ? err.message
          : "Произошла неизвестная ошибка"
      );
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  }

  // ==========================================================
  // STOP
  // ==========================================================

  function stopGeneration() {
    abortControllerRef.current?.abort();

    setIsGenerating(false);
  }

  // ==========================================================
  // KEYBOARD
  // ==========================================================

  function handleKeyDown(
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ) {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();

      sendMessage();
    }
  }

  // ==========================================================
  // RENDER CONTENT
  // ==========================================================

  function renderMessageContent(
    content: MessageContent
  ) {
    if (typeof content === "string") {
      return content;
    }

    return content.map(
      (item, index) => {
        if (item.type === "text") {
          return (
            <span key={index}>
              {item.text}
            </span>
          );
        }

        if (
          item.type === "image_url"
        ) {
          return (
            <img
              key={index}
              src={item.image_url.url}
              alt="Uploaded image"
              className="message-image"
            />
          );
        }

        return null;
      }
    );
  }

  // ==========================================================
  // UI
  // ==========================================================

  return (
    <div className="app">

      <header className="header">

        <div>
          <h1>
            Local LLM Chat
          </h1>

          <span className="subtitle">
            LM Studio
          </span>
        </div>

        <div className="status">

          <span
            className={`status-dot ${
              lmStudioAvailable
                ? "online"
                : "offline"
            }`}
          />

          {lmStudioAvailable
            ? "LM Studio Online"
            : "LM Studio Offline"}

        </div>

      </header>

      <main
        className="chat"
        ref={chatRef}
        onScroll={handleChatScroll}
      >

        {messages.length === 0 ? (

          <div className="empty">

            <h2>
              Local LLM
            </h2>

            <p>
              {lmStudioAvailable
                ? "Модель готова к работе."
                : "Запусти LM Studio и Local Server, чтобы начать."}
            </p>

          </div>

        ) : (

          messages.map(
            (message, index) => (

              <div
                key={index}
                className={`message message-enter ${
                  message.role === "user"
                    ? "user"
                    : "assistant"
                }`}
              >

                <div className="message-role">
                  {message.role === "user"
                    ? "You"
                    : "Assistant"}
                </div>

                <div className="message-content">

                  {message.content &&
                  typeof message.content !==
                    "string"

                    ? renderMessageContent(
                        message.content
                      )

                    : message.content ||
                      (
                        isGenerating &&
                        index ===
                          messages.length - 1
                          ? "..."
                          : ""
                      )}

                </div>

              </div>
            )
          )

        )}

      </main>

      <footer className="composer">

        {error && (
          <div className="error">
            {error}
          </div>
        )}

        {selectedImage && (

          <div className="image-preview">

            <img
              src={selectedImage}
              alt="Preview"
            />

            <button
              type="button"
              onClick={removeImage}
              disabled={isGenerating}
            >
              ×
            </button>

          </div>

        )}

        <div className="controls">

          <select
            value={selectedModel}
            onChange={event =>
              setSelectedModel(
                event.target.value
              )
            }
            disabled={
              isGenerating ||
              models.length === 0
            }
          >

            {models.length === 0 ? (

              <option value="">
                Нет доступных моделей
              </option>

            ) : (

              models.map(model => (

                <option
                  key={model.id}
                  value={model.id}
                >
                  {model.id}
                </option>

              ))

            )}

          </select>

          <button
            onClick={loadModels}
            disabled={isGenerating}
          >
            Refresh
          </button>

        </div>

        <div className="input-row">

          <label
            className="image-button"
            title="Добавить изображение"
          >

            📎

            <input
              type="file"
              accept="image/*"
              onChange={handleImageChange}
              disabled={
                isGenerating ||
                !lmStudioAvailable
              }
              hidden
            />

          </label>

          <textarea
            value={input}
            onChange={event =>
              setInput(
                event.target.value
              )
            }
            onKeyDown={handleKeyDown}
            placeholder={
              lmStudioAvailable
                ? "Напиши сообщение..."
                : "LM Studio Offline"
            }
            disabled={
              !lmStudioAvailable ||
              isGenerating
            }
            rows={1}
          />

          {isGenerating ? (

            <button
              className="stop"
              onClick={stopGeneration}
            >
              Stop
            </button>

          ) : (

            <button
              className="send"
              onClick={sendMessage}
              disabled={
                (!input.trim() &&
                  !selectedImage) ||
                !selectedModel ||
                !lmStudioAvailable
              }
            >
              Send
            </button>

          )}

        </div>

      </footer>

    </div>
  );
}

export default App;