import type { ChatMessage as ChatMessageType } from "../types";

interface Props {
  message: ChatMessageType;
  streaming?: boolean;
}

export function ChatMessage({ message, streaming }: Props) {
  const isUser = message.role === "user";
  const wrapperClass = isUser ? "flex justify-end" : "flex justify-start";
  const bubbleClass = isUser
    ? "bg-blue-600 text-white"
    : "bg-white text-gray-800 border border-gray-200";

  return (
    <div className={wrapperClass}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 shadow-sm ${bubbleClass}`}
      >
        <div className="whitespace-pre-wrap break-words text-sm">
          {message.content || (streaming ? <em className="opacity-60">…</em> : "")}
          {streaming && message.content ? (
            <span className="ml-1 inline-block h-3 w-1 animate-pulse bg-current align-middle" />
          ) : null}
        </div>
        {message.cancelled ? (
          <div className="mt-1 text-xs italic opacity-70">(stopped)</div>
        ) : null}
      </div>
    </div>
  );
}

export default ChatMessage;
