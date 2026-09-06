import * as React from 'react';

/**
 * Props for the angular toggle switch.
 *
 * @startingPoint section="Forms" subtitle="Angular on/off toggle" viewport="700x120"
 */
export interface SwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  /** Controlled checked state. */
  checked?: boolean;
  /** Text label rendered after the track. */
  label?: React.ReactNode;
  /** Active-state color. @default "cyan" */
  accent?: 'cyan' | 'blue';
  disabled?: boolean;
}

/**
 * Angular toggle switch with cyan glow when on.
 */
export function Switch(props: SwitchProps): JSX.Element;
