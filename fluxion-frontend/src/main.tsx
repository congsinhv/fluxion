import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "@/App";
import "@/index.css";

// Explicit null check — no non-null assertion (code-standards §4.2)
const root = document.getElementById("root");
if (!root) throw new Error("root element not found");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
