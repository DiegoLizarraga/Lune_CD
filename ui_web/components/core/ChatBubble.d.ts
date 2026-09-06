import * as React from 'react';

/**
 * Props for a single chat row.
 *
 * @startingPoint section="Chat" subtitle="User + assistant message bubbles" viewport="700x260"
 */
export interface ChatBubbleProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Who is speaking. @default "bot" */
  role?: 'bot' | 'user';
  /** Provider tint for bot bubbles. @default "local" */
  provider?: 'local' | 'cloud';
  /** Sender label (bot only). Defaults to "Lune · Local/Nube". */
  sender?: React.ReactNode;
  /** Avatar node rendered beside the bubble. */
  avatar?: React.ReactNode;
  /** Timestamp string. */
  time?: string;
  /** Show the blinking stream caret. @default false */
  streaming?: boolean;
  children?: React.ReactNode;
}

/**
 * One chat row — avatar plus an angular speech bubble.
 */
export function ChatBubble(props: ChatBubbleProps): JSX.Element;
