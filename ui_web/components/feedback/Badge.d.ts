import * as React from 'react';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Color. @default "cyan" */
  variant?: 'cyan' | 'blue' | 'yellow' | 'danger' | 'ink';
  /** Outline (transparent fill) instead of solid. @default false */
  outline?: boolean;
  children?: React.ReactNode;
}

/**
 * Compact mono tag/label chip with clipped corner.
 *
 * @startingPoint section="Feedback" subtitle="Mono tag chips, solid & outline" viewport="700x120"
 */
export function Badge(props: BadgeProps): JSX.Element;
