import type { ReactNode } from "react";

interface StatusMessageProps {
  tone: "error" | "warning";
  title?: string;
  children: ReactNode;
}

export function StatusMessage({ tone, title, children }: StatusMessageProps) {
  return (
    <div className={`status status--${tone}`} role={tone === "error" ? "alert" : "status"}>
      {title && <strong>{title}</strong>}
      <p>{children}</p>
    </div>
  );
}
