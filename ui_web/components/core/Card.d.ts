import * as React from 'react';

/**
 * Props for the notched surface panel.
 *
 * @startingPoint section="Core" subtitle="Notched surface panel with eyebrow + title" viewport="700x260"
 */
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Small uppercase mono label above the title. */
  eyebrow?: React.ReactNode;
  /** Display-font card title. */
  title?: React.ReactNode;
  /** Border/accent tone. @default "default" */
  tone?: 'default' | 'raised' | 'cyan' | 'blue' | 'yellow';
  /** Apply the signature notched corners. @default true */
  notch?: boolean;
  /** Technical grid background texture. @default false */
  grid?: boolean;
  /** Scanline overlay. @default false */
  scan?: boolean;
  /** Cyan corner tick on the cut corner. @default false */
  tick?: boolean;
  children?: React.ReactNode;
}

/**
 * Notched Shibuya-Punk surface panel — base container for content.
 */
export function Card(props: CardProps): JSX.Element;
