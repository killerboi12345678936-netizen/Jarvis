import type { ReactNode } from "react";
import { X } from "lucide-react";

type SlideOverProps = {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
};

export function SlideOver({
  title,
  subtitle,
  onClose,
  children,
}: SlideOverProps) {
  return (
    <div className="slideover-overlay" onClick={onClose}>
      <aside
        className="slideover"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="slideover-header">
          <div>
            <h2>{title}</h2>
            {subtitle && <span>{subtitle}</span>}
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            title="Close panel"
          >
            <X size={17} />
          </button>
        </header>

        <div className="slideover-body">{children}</div>
      </aside>
    </div>
  );
}
