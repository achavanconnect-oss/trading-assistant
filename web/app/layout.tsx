import type { ReactNode } from 'react';
import './globals.css';

export const metadata = {
  title: 'Trading Assistant',
  description: 'Read-only trading assistant. Cannot place trades. Not financial advice.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
