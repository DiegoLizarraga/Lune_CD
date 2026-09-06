import * as React from 'react';

export interface StatusPillProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Connection / activity state. @default "live" */
  status?: 'live' | 'busy' | 'error' | 'off';
  /** Override the default Spanish label. */
  children?: React.ReactNode;
}

/**
 * Rounded pill with a pulsing LED for connection / activity status.
 *
 * @startingPoint section="Feedback" subtitle="Pulsing-LED status pill" viewport="700x110"
 */
export function StatusPill(props: StatusPillProps): JSX.Element;
