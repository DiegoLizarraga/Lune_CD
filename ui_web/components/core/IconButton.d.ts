import * as React from 'react';

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible label (also used as tooltip). */
  label?: string;
  /** Visual style. @default "ghost" */
  variant?: 'ghost' | 'solid' | 'cyan' | 'danger';
  /** Size. @default "md" */
  size?: 'sm' | 'md' | 'lg';
  /** Apply clipped corner. @default false */
  clip?: boolean;
  /** Active/selected styling. @default false */
  active?: boolean;
  /** Icon node (inline SVG). */
  children?: React.ReactNode;
}

/** Square icon-only button. Provide an inline SVG icon as children. */
export function IconButton(props: IconButtonProps): JSX.Element;
