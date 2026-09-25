import {
  Alert,
  AlertDescription,
  Button,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Skeleton,
} from "@databricks/appkit-ui/react";
import { Check, ChevronsUpDown } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Account } from "../types";

interface AccountComboboxProps {
  accounts: Account[];
  accountId: string;
  busy?: boolean;
  onAccountChange: (accountId: string) => void;
}

export function AccountCombobox({ accounts, accountId, busy, onAccountChange }: AccountComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [remote, setRemote] = useState<Account[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const selected = accounts.find((account) => account.account_id === accountId) ?? null;

  useEffect(() => {
    if (!open) {
      setQuery("");
      setRemote(null);
      setLoading(false);
      setError("");
      return;
    }

    const normalized = query.trim();
    if (normalized.length < 2) {
      setRemote(null);
      setLoading(false);
      setError("");
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError("");
      void api.accounts(normalized, controller.signal)
        .then((result) => {
          if (!controller.signal.aborted) setRemote(result.results);
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setRemote(null);
            setError("Search is temporarily limited. Showing available accounts.");
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 180);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [open, query]);

  const changeQuery = (nextQuery: string) => {
    setQuery(nextQuery);
    if (nextQuery.trim().length >= 2) {
      setRemote(null);
      setError("");
    }
  };

  const visible = useMemo(() => {
    if (remote) return remote;
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return accounts.slice(0, 20);
    return accounts
      .filter((account) => accountSearchText(account).includes(normalized))
      .slice(0, 20);
  }, [accounts, query, remote]);

  const choose = (nextAccountId: string) => {
    setOpen(false);
    setQuery("");
    if (nextAccountId !== accountId) onAccountChange(nextAccountId);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id="account-selector"
          type="button"
          variant="outline"
          role="combobox"
          aria-label="Select quote account"
          aria-expanded={open}
          className="account-picker-trigger"
          style={{ gridTemplateColumns: "minmax(0, 1fr) max-content" }}
          disabled={busy || accounts.length === 0}
        >
          <span>{selected?.name || "Select an account"}</span>
          <ChevronsUpDown aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="account-picker-popover">
        <Command shouldFilter={false} label="Quote accounts">
          <CommandInput value={query} onValueChange={changeQuery} placeholder="Search accounts…" />
          <CommandList label="Account results">
            {error && (
              <Alert className="account-search-alert">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {loading ? (
              <div className="account-search-skeleton" role="status" aria-label="Searching accounts">
                {[0, 1, 2].map((row) => <Skeleton key={row} />)}
              </div>
            ) : (
              <>
                <CommandEmpty>
                  {query.trim() ? "No accounts match that search." : "No accounts are available."}
                </CommandEmpty>
                <CommandGroup>
                  {visible.map((account) => {
                    const summary = accountSummary(account);
                    return (
                      <CommandItem
                        value={account.account_id}
                        key={account.account_id}
                        onSelect={choose}
                        className="account-result"
                      >
                        <Check data-selected={account.account_id === accountId || undefined} aria-hidden="true" />
                        <span>
                          <strong>{account.name}</strong>
                          {summary && <small>{summary}</small>}
                        </span>
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function accountSummary(account: Account): string {
  const location = [account.city, account.state].filter(Boolean).join(", ");
  return [location, account.specialty, account.segment].filter(Boolean).join(" · ");
}

function accountSearchText(account: Account): string {
  return [account.name, account.city, account.state, account.specialty, account.segment]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
}
