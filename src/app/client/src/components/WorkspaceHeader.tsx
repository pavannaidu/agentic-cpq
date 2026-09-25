import {
  Avatar,
  AvatarFallback,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@databricks/appkit-ui/react";
import { ChevronDown, FilePlus2, History, Info, Moon, Settings2, Sun } from "lucide-react";
import type { Account, CurrentUser, ViewRole } from "../types";
import { AccountCombobox } from "./AccountCombobox";

interface WorkspaceHeaderProps {
  accounts: Account[];
  accountId: string;
  user: CurrentUser | null;
  role: ViewRole;
  allowedRoles: ViewRole[];
  dark: boolean;
  busy?: boolean;
  onAccountChange: (accountId: string) => void;
  onRoleChange: (role: ViewRole) => void;
  onOpenAdmin: () => void;
  onNewQuote: () => void;
  newQuoteDisabled?: boolean;
  onHistory: () => void;
  onToggleTheme: () => void;
}

export function WorkspaceHeader({
  accounts,
  accountId,
  user,
  role,
  allowedRoles,
  dark,
  busy,
  onAccountChange,
  onRoleChange,
  onOpenAdmin,
  onNewQuote,
  newQuoteDisabled,
  onHistory,
  onToggleTheme,
}: WorkspaceHeaderProps) {
  const displayName = user?.username || user?.email || "Signed in";
  const initials = displayName
    .split(/[\s.@_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "AC";
  const roleOptions = allowedRoles.length > 0 ? allowedRoles : [role];

  const changeRole = (value: string) => {
    if (
      !busy
      && (value === "seller" || value === "manager")
      && roleOptions.includes(value)
      && value !== role
    ) {
      onRoleChange(value);
    }
  };

  return (
    <header className="workspace-header">
      <div className="brand-lockup">
        <h1>Agentic CPQ</h1>
      </div>

      <div className="header-context">
        <div className="account-field">
          <AccountCombobox
            accounts={accounts}
            accountId={accountId}
            busy={busy}
            onAccountChange={onAccountChange}
          />
        </div>
      </div>

      <div className="header-actions">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="default"
              onClick={onNewQuote}
              className="new-quote-button"
              aria-label="New quote"
              disabled={busy || newQuoteDisabled}
            >
              <FilePlus2 aria-hidden="true" />
              <span>New quote</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Start a new quote</TooltipContent>
        </Tooltip>

        <Button type="button" variant="outline" onClick={onHistory} className="history-button" aria-label="Open quote history" disabled={busy}>
          <History aria-hidden="true" />
          <span>History</span>
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="outline"
              className="identity-control"
              aria-label={`User menu for ${displayName}, ${roleName(role)} role`}
            >
              <Avatar>
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
              <span className="identity-copy">
                <strong>{firstName(displayName)}</strong>
                <small>{roleName(role)}</small>
              </span>
              <ChevronDown className="identity-chevron" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="bottom" sideOffset={6} className="identity-menu" loop>
            <DropdownMenuLabel className="identity-menu-profile">
              <strong>{displayName}</strong>
              {user?.email && user.email !== displayName && <span>{user.email}</span>}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Role</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={role} onValueChange={changeRole} aria-label="Workspace view">
              {roleOptions.map((allowedRole) => (
                <DropdownMenuRadioItem
                  value={allowedRole}
                  textValue={roleName(allowedRole)}
                  disabled={busy}
                  key={allowedRole}
                >
                  {roleName(allowedRole)}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onToggleTheme} disabled={busy}>
              {dark ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
              {dark ? "Light theme" : "Dark theme"}
            </DropdownMenuItem>
            {user?.can_manage && (
              <DropdownMenuItem onSelect={onOpenAdmin} disabled={busy}>
                <Settings2 aria-hidden="true" />
                Workspace settings
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <a href="/info">
                <Info aria-hidden="true" />
                About Agentic CPQ
              </a>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

function firstName(value: string): string {
  return value.split(/[\s@.]/)[0] || value;
}

function roleName(role: ViewRole): string {
  return role === "manager" ? "Manager" : "Seller";
}
