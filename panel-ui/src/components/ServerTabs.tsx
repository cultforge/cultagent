import { NavLink, useLocation } from "react-router-dom";
import { SERVER_TABS, tabFromPath } from "../lib/servers";

export function ServerTabs({ serverId }: { serverId: string }) {
  const { pathname } = useLocation();
  const active = tabFromPath(pathname);

  return (
    <nav className="border-b border-border">
      <ul className="m-0 flex list-none gap-0.5 overflow-x-auto">
        {SERVER_TABS.map((tab) => {
          const href = tab.path(serverId);
          const isActive = tab.id === active;
          return (
            <li key={tab.id}>
              <NavLink
                to={href}
                end={tab.id === "overview"}
                className={() =>
                  [
                    "inline-flex items-center whitespace-nowrap border-b-2 px-3.5 py-2.5 text-[13px] font-medium transition-colors",
                    isActive
                      ? "border-neon text-text"
                      : "border-transparent text-text-dim hover:text-text",
                  ].join(" ")
                }
              >
                {tab.label}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
