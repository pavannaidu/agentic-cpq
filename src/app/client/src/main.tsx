import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { InfoPage } from "./InfoPage";
import "./styles.css";

const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
const Page = pathname === "/info" ? InfoPage : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
