import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as ChatMessageType } from "../types";

interface Props {
  message: ChatMessageType;
  streaming?: boolean;
}

// Elements the advisor is allowed to emit. No raw HTML, no images, no
// interactive links — LLM chat output shouldn't be navigable.
const ALLOWED_MARKDOWN_ELEMENTS = [
  "p",
  "br",
  "strong",
  "em",
  "del",
  "code",
  "pre",
  "ul",
  "ol",
  "li",
  "blockquote",
  "h1",
  "h2",
  "h3",
  "h4",
  "hr",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
];

// Minimal Tailwind styling applied per-element so lists and inline code
// render correctly without needing @tailwindcss/typography.
const MARKDOWN_COMPONENTS = {
  p: (props: React.HTMLAttributes<HTMLParagraphElement>) => (
    <p className="my-1 first:mt-0 last:mb-0" {...props} />
  ),
  ul: (props: React.HTMLAttributes<HTMLUListElement>) => (
    <ul className="my-1 list-disc space-y-0.5 pl-5" {...props} />
  ),
  ol: (props: React.HTMLAttributes<HTMLOListElement>) => (
    <ol className="my-1 list-decimal space-y-0.5 pl-5" {...props} />
  ),
  li: (props: React.HTMLAttributes<HTMLLIElement>) => (
    <li className="leading-snug" {...props} />
  ),
  strong: (props: React.HTMLAttributes<HTMLElement>) => (
    <strong className="font-semibold" {...props} />
  ),
  em: (props: React.HTMLAttributes<HTMLElement>) => (
    <em className="italic" {...props} />
  ),
  code: (props: React.HTMLAttributes<HTMLElement>) => (
    <code
      className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[0.8em] text-gray-900"
      {...props}
    />
  ),
  pre: (props: React.HTMLAttributes<HTMLPreElement>) => (
    <pre
      className="my-2 overflow-x-auto rounded bg-gray-100 p-2 font-mono text-xs text-gray-900"
      {...props}
    />
  ),
  blockquote: (props: React.HTMLAttributes<HTMLQuoteElement>) => (
    <blockquote
      className="my-1 border-l-2 border-gray-300 pl-3 italic opacity-80"
      {...props}
    />
  ),
  h1: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h1 className="mt-2 mb-1 text-base font-semibold" {...props} />
  ),
  h2: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h2 className="mt-2 mb-1 text-sm font-semibold" {...props} />
  ),
  h3: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h3 className="mt-1 mb-0.5 text-sm font-semibold" {...props} />
  ),
  table: (props: React.HTMLAttributes<HTMLTableElement>) => (
    <table className="my-2 w-full border-collapse text-xs" {...props} />
  ),
  th: (props: React.ThHTMLAttributes<HTMLTableCellElement>) => (
    <th
      className="border border-gray-300 bg-gray-50 px-2 py-1 text-left font-semibold"
      {...props}
    />
  ),
  td: (props: React.TdHTMLAttributes<HTMLTableCellElement>) => (
    <td className="border border-gray-300 px-2 py-1" {...props} />
  ),
};

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
        <div className="break-words text-sm">
          {isUser ? (
            // User messages render as plain text with preserved whitespace;
            // whatever they typed is shown verbatim.
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : message.content ? (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              allowedElements={ALLOWED_MARKDOWN_ELEMENTS}
              unwrapDisallowed
              components={MARKDOWN_COMPONENTS}
            >
              {message.content}
            </ReactMarkdown>
          ) : streaming ? (
            <em className="opacity-60">…</em>
          ) : null}
          {streaming && !isUser && message.content ? (
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
