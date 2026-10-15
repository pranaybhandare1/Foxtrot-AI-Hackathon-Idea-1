/** Right-hand side panel (Escape or the scrim closes it). */

import { useEffect, type ReactNode } from "react";
import { Icons } from "./Icons";

export function Drawer({ title, sub, onClose, children }: { title: ReactNode; sub?: ReactNode; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="glass drawer" role="dialog" aria-modal>
        <div className="drawer-head spread">
          <div>
            <div className="card-title" style={{ fontSize: 16 }}>{title}</div>
            {sub && <div className="card-sub">{sub}</div>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icons.close /></button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}
