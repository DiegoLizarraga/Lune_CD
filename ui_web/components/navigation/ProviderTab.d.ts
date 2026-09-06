import * as React from 'react';

/**
 * Props for the sidebar AI-provider selector row.
 *
 * @startingPoint section="Navigation" subtitle="Provider selector rows" viewport="700x200"
 */
export interface ProviderTabProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Icon node (inline SVG) for the provider. */
  icon?: React.ReactNode;
  /** Provider name, e.g. "Lune AI (Local)". */
  name?: React.ReactNode;
  /** Sub-label, e.g. "Modelo Offline". */
  desc?: React.ReactNode;
  /** Active accent. @default "cyan" */
  accent?: 'cyan' | 'blue';
  /** Selected state. @default false */
  active?: boolean;
}

/**
 * Sidebar AI-provider selector row (Nube / Local) with active accent + LED.
 */
export function ProviderTab(props: ProviderTabProps): JSX.Element;
