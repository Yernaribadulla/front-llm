import { useEffect, useRef, useState } from "react";

type Model = {
  id: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
};

const API_URL = "";

function App() {
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [lmStudioAvailable, setLmStudioAvailable] = useState(false);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState("");

  const abortControllerRef = useRef<AbortController | null>(null);

  async function loadModels() {
  try {
    console.log("FETCH:", `${API_URL}/api/models`);

    const response = await fetch(`${API_URL}/api/models`);

    console.log("STATUS:", response.status);
    console.log("OK:", response.ok);

    const data = await response.json();

    console.log("DATA:", data);

    setModels(data.models);
    setLmStudioAvailable(data.lm_studio_available);

    if (data.models.length > 0) {
      setSelectedModel(data.models[0].id);
    }
  } catch (error) {
    console.error("ERROR:", error);

    setLmStudioAvailable(false);
    setModels([]);
  }
}

  useEffect(() => {
    loadModels();
  }, []);

  async function sendMessage() {
    const text = input.trim();

    if (!text || isGenerating || !selectedModel) {
      return;
    }

    setError("");
    setInput("");

    const userMessage: Message = {
      role: "user",
      content: text,
    };

    const newMessages = [...messages, userMessage];

    setMessages([
      ...newMessages,
      {
        role: "assistant",
        content: "",
      },
    ]);

    setIsGenerating(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: selectedModel,
          messages: newMessages,
          system_prompt: "Ты полезный ассистент. Отвечай ясно и по существу.",
          params: {
            temperature: 0.7,
            max_tokens: 1024,
            top_p: 1.0,
          },
        }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error("Не удалось подключиться к backend");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const event of events) {
          const lines = event.split("\n");

          let eventType = "";
          let data = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7);
            }

            if (line.startsWith("data: ")) {
              data = line.slice(6);
            }
          }

          if (!data) {
            continue;
          }

          const parsed = JSON.parse(data);

          if (eventType === "token") {
            setMessages((current) => {
              const updated = [...current];
              const last = updated.length - 1;

              updated[last] = {
                ...updated[last],
                content: updated[last].content + parsed.content,
              };

              return updated;
            });
          }

          if (eventType === "error") {
            setError(parsed.message);
          }

          if (eventType === "done") {
            setIsGenerating(false);
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }

      setError(
        err instanceof Error ? err.message : "Произошла неизвестная ошибка"
      );
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  }

  function stopGeneration() {
    abortControllerRef.current?.abort();
    setIsGenerating(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Local LLM Chat</h1>
          <span className="subtitle">LM Studio</span>
        </div>

        <div className="status">
          <span
            className={`status-dot ${
              lmStudioAvailable ? "online" : "offline"
            }`}
          />

          {lmStudioAvailable ? "LM Studio Online" : "LM Studio Offline"}
        </div>
      </header>

      <main className="chat">
        {messages.length === 0 ? (
          <div className="empty">
            <h2>Local LLM</h2>

            <p>
              {lmStudioAvailable
                ? "Модель готова к работе."
                : "Запусти LM Studio и Local Server, чтобы начать."}
            </p>
          </div>
        ) : (
          messages.map((message, index) => (
            <div
              key={index}
              className={`message ${
                message.role === "user" ? "user" : "assistant"
              }`}
            >
              <div className="message-role">
                {message.role === "user" ? "You" : "Assistant"}
              </div>

              <div className="message-content">
                {message.content || (isGenerating ? "..." : "")}
              </div>
            </div>
          ))
        )}
      </main>

      <footer className="composer">
        {error && <div className="error">{error}</div>}

        <div className="controls">
          <select
            value={selectedModel}
            onChange={(event) => setSelectedModel(event.target.value)}
            disabled={isGenerating || models.length === 0}
          >
            {models.length === 0 ? (
              <option value="">Нет доступных моделей</option>
            ) : (
              models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.id}
                </option>
              ))
            )}
          </select>

          <button onClick={loadModels} disabled={isGenerating}>
            Refresh
          </button>
        </div>

        <div className="input-row">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              lmStudioAvailable
                ? "Напиши сообщение..."
                : "LM Studio Offline"
            }
            disabled={!lmStudioAvailable || isGenerating}
            rows={1}
          />

          {isGenerating ? (
            <button className="stop" onClick={stopGeneration}>
              Stop
            </button>
          ) : (
            <button
              className="send"
              onClick={sendMessage}
              disabled={
                !input.trim() || !selectedModel || !lmStudioAvailable
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
