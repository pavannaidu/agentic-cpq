import {
  Alert,
  AlertDescription,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Skeleton,
  Spinner,
} from "@databricks/appkit-ui/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { currency } from "../domain";
import type { Product, ViewRole } from "../types";

interface ProductDialogProps {
  open: boolean;
  products: Product[];
  role: ViewRole;
  onOpenChange: (open: boolean) => void;
  onAdd: (product: Product) => Promise<void>;
}

export function ProductDialog({ open, products, role, onOpenChange, onAdd }: ProductDialogProps) {
  const [query, setQuery] = useState("");
  const [remote, setRemote] = useState<Product[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [addError, setAddError] = useState("");
  const [addingSku, setAddingSku] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setRemote(null);
      setLoading(false);
      setSearchError("");
      setAddError("");
      setAddingSku(null);
      return;
    }

    const normalized = query.trim();
    if (normalized.length < 2) {
      setRemote(null);
      setLoading(false);
      setSearchError("");
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setSearchError("");
      void api.products(normalized, role, controller.signal)
        .then((result) => {
          if (!controller.signal.aborted) setRemote(result.results);
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setRemote(null);
            setSearchError("Search is temporarily limited. Showing available products.");
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 220);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [open, query, role]);

  const changeQuery = (nextQuery: string) => {
    setQuery(nextQuery);
    setAddError("");
    if (nextQuery.trim().length >= 2) {
      setRemote(null);
      setSearchError("");
    }
  };

  const visibleProducts = useMemo(() => {
    if (remote) return remote;
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return products.slice(0, 24);
    return products
      .filter((product) => (
        `${product.sku} ${product.title} ${product.category} ${product.description ?? ""}`
          .toLocaleLowerCase()
          .includes(normalized)
      ))
      .slice(0, 24);
  }, [products, query, remote]);

  const add = async (product: Product) => {
    setAddingSku(product.sku);
    setAddError("");
    try {
      await onAdd(product);
      onOpenChange(false);
    } catch {
      setAddError("Unable to add this product. Please try again.");
    } finally {
      setAddingSku(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="product-dialog">
        <DialogHeader>
          <DialogTitle>Add product</DialogTitle>
          <DialogDescription>Account pricing is applied automatically.</DialogDescription>
        </DialogHeader>

        <Command shouldFilter={false} label="Product catalog" className="product-command">
          <CommandInput
            value={query}
            onValueChange={changeQuery}
            placeholder="Search products, SKUs, or categories…"
          />
          <CommandList className="product-command-list" label="Catalog results">
            {searchError && (
              <Alert className="product-search-alert">
                <AlertDescription>{searchError}</AlertDescription>
              </Alert>
            )}
            {addError && (
              <Alert variant="destructive" className="product-add-alert">
                <AlertDescription>{addError}</AlertDescription>
              </Alert>
            )}

            {loading ? (
              <div className="product-search-skeleton" role="status" aria-label="Searching catalog">
                {[0, 1, 2].map((row) => <Skeleton key={row} />)}
              </div>
            ) : (
              <>
                <CommandEmpty>
                  {query.trim()
                    ? "No catalog products match that search."
                    : "No catalog products are available."}
                </CommandEmpty>
                <CommandGroup>
                  {visibleProducts.map((product) => (
                    <CommandItem
                      value={product.sku}
                      key={product.sku}
                      disabled={addingSku != null}
                      onSelect={() => void add(product)}
                      className="product-result"
                      style={{ gridTemplateColumns: "minmax(0, 1fr) max-content" }}
                    >
                      <div className="product-result-copy">
                        <strong>{product.title}</strong>
                        <span>{product.sku} · {product.category}</span>
                      </div>
                      <div className="product-result-meta">
                        {product.warranty_eligible && <span className="muted-copy">Care plan eligible</span>}
                        <strong>{currency.format(Number(product.unit_price ?? product.list_price ?? 0))}</strong>
                        {addingSku === product.sku && <Spinner />}
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
