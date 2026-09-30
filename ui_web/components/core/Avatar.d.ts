import * as React from 'react';

export interface AvatarProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Image URL (Lune portrait / user photo). */
  src?: string;
  alt?: string;
  /** Fallback initials when no image. */
  initials?: string;
  /** Render the gradient bot mark. @default false */
  bot?: boolean;
  /** Size. @default "md" */
  size?: 'sm' | 'md' | 'lg' | 'xl';
  /** Colored ring + glow. */
  ring?: 'cyan' | 'blue' | 'yellow';
  /** Show online status dot. @default false */
  online?: boolean;
}

/** Clipped-corner avatar for Lune, user initials, or bot mark. */
export function Avatar(props: AvatarProps): JSX.Element;
