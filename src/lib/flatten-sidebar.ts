/**
 * Flattens Starlight sidebar entries into the list of links they contain.
 * Starlight's own helper lives in an internal module that is not part of
 * its public exports, so overrides use this local copy.
 */
type SidebarEntry = { type: string; entries?: SidebarEntry[]; isCurrent?: boolean };

export function flattenSidebar<T extends SidebarEntry>(sidebar: T[]): T[] {
  return sidebar.flatMap((entry) =>
    entry.type === "group" ? flattenSidebar((entry.entries ?? []) as T[]) : [entry],
  );
}
