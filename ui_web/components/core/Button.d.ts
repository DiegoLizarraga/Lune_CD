import * as React from 'react';

/**
 * Props for the angular Shibuya-Punk action button.
 *
 * @startingPoint section="Core" subtitle="Clipped-corner action button, 5 variants" viewport="700x200"
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual role. @default "primary" */
  variant?: 'primary' | 'secondary' | 'pop' | 'ghost' | 'danger';
  /** Control height. @default "md" */
  size?: 'sm' | 'md' | 'lg';
  /** Stretch to container width. @default false */
  block?: boolean;
  /** Render the hard print-shadow behind the button. @default true */
  shadow?: boolean;
  /** Element rendered before the label (icon/glyph). */
  leading?: React.ReactNode;
  /** Element rendered after the label. */
  trailing?: React.ReactNode;
  children?: React.ReactNode;
}

/**
 * Angular Shibuya-Punk action button with clipped corner and offset shadow.
 */
export function Button(props: ButtonProps): JSX.Element;
