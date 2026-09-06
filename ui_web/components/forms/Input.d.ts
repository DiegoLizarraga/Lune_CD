import * as React from 'react';

/**
 * Props for the clipped-corner text field.
 *
 * @startingPoint section="Forms" subtitle="Text field with label, hint & focus glow" viewport="700x180"
 */
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement & HTMLTextAreaElement> {
  /** Uppercase mono label above the field. */
  label?: React.ReactNode;
  /** Show required asterisk. @default false */
  required?: boolean;
  /** Leading glyph/icon inside the field (text inputs only). */
  leading?: React.ReactNode;
  /** Helper or error text below the field. */
  hint?: React.ReactNode;
  /** Error styling. @default false */
  error?: boolean;
  /** Render a multi-line textarea instead of an input. @default false */
  textarea?: boolean;
}

/**
 * Clipped-corner text field with cyan focus glow, label, hint and error states.
 */
export function Input(props: InputProps): JSX.Element;
