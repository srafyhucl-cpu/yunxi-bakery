/**
 * UMP（统一消息协议）富媒体标记解析工具。
 *
 * 格式：[UMP: type=card&id=xxx&title=xxx&price=xxx&src=xxx&url=xxx]
 */

export interface UmpCard {
  type: "card";
  id: string;
  title: string;
  price: string;
  src: string;
  url: string;
}

export type MessageSegment =
  | { type: "text"; value: string }
  | UmpCard;

const UMP_RE = /\[UMP:\s*([^\]]+)\]/g;

/**
 * 将消息内容解析为文本段和卡片段的混合列表。
 */
export function parseMessageSegments(content: string): MessageSegment[] {
  const segments: MessageSegment[] = [];
  let lastIndex = 0;

  for (const match of content.matchAll(UMP_RE)) {
    const start = match.index!;
    if (start > lastIndex) {
      const text = content.slice(lastIndex, start).trim();
      if (text) {
        segments.push({ type: "text", value: text });
      }
    }

    const card = parseUmpCard(match[1]);
    if (card) {
      segments.push(card);
    }

    lastIndex = start + match[0].length;
  }

  const remaining = content.slice(lastIndex).trim();
  if (remaining) {
    segments.push({ type: "text", value: remaining });
  }

  return segments.length > 0 ? segments : [{ type: "text", value: content }];
}

function parseUmpCard(raw: string): UmpCard | null {
  const params = new URLSearchParams(raw.trim());
  if (params.get("type") !== "card") {
    return null;
  }
  return {
    type: "card",
    id: params.get("id") ?? "",
    title: decodeURIComponent(params.get("title") ?? ""),
    price: params.get("price") ?? "",
    src: decodeURIComponent(params.get("src") ?? ""),
    url: decodeURIComponent(params.get("url") ?? ""),
  };
}
