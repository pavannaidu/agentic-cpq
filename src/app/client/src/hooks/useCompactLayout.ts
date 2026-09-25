import { useEffect, useState } from "react";

const QUERY = "(max-width: 1023px)";

export function useCompactLayout(): boolean {
  const [compact, setCompact] = useState(() => (typeof window === "undefined" ? false : window.matchMedia(QUERY).matches));

  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const update = () => setCompact(media.matches);
    media.addEventListener("change", update);
    update();
    return () => media.removeEventListener("change", update);
  }, []);

  return compact;
}
