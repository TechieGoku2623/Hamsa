import { useRef, useState } from "react";

export default function Composer({ onSend, onTyping, placeholder, disabled }: {
  onSend: (text: string) => Promise<void> | void;
  onTyping?: () => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const lastTyping = useRef(0);

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setText("");
    try {
      await onSend(t);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        rows={1}
        value={text}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => {
          setText(e.target.value);
          const now = Date.now();
          if (onTyping && now - lastTyping.current > 2000) {
            lastTyping.current = now;
            onTyping();
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <button className="send" disabled={disabled || busy || !text.trim()} aria-label="Send">➤</button>
    </form>
  );
}
