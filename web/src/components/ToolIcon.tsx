import clsx from "clsx";
import { Captions, Crop, Download, Wand2 } from "lucide-react";
import type { CatalogTool, ToolId } from "@/lib/catalog";

export const TOOL_ICONS: Record<ToolId, React.ComponentType<{ className?: string }>> = {
  download: Download,
  clips: Wand2,
  captions: Captions,
  reframe: Crop,
};

/** The tool's icon on its own coloured tile. */
export function ToolTile({ tool, size = "md" }: { tool: CatalogTool; size?: "sm" | "md" | "lg" }) {
  const Icon = TOOL_ICONS[tool.id];
  return (
    <span
      className={clsx(
        "grid shrink-0 place-items-center",
        tool.tone.tile,
        size === "sm" && "size-8 rounded-lg",
        size === "md" && "size-10 rounded-xl",
        size === "lg" && "size-12 rounded-2xl",
      )}
    >
      <Icon className={size === "lg" ? "size-6" : size === "md" ? "size-5" : "size-4"} />
    </span>
  );
}
