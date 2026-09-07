import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import "./styles/global.css";

const rootElement = document.getElementById("root");

if (rootElement === null) {
  throw new Error("应用根节点不存在。");
}

function suppressAuthoringAutocomplete(root: ParentNode): void {
  root
    .querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
      'input[type="text"], input:not([type]), textarea',
    )
    .forEach((field) => {
      field.setAttribute("autocomplete", "off");
    });
}

const autocompleteObserver = new MutationObserver((records) => {
  for (const record of records) {
    for (const node of record.addedNodes) {
      if (node instanceof Element) {
        if (node.matches('input[type="text"], input:not([type]), textarea')) {
          node.setAttribute("autocomplete", "off");
        }
        suppressAuthoringAutocomplete(node);
      }
    }
  }
});

autocompleteObserver.observe(rootElement, { childList: true, subtree: true });

createRoot(rootElement).render(
  <StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </StrictMode>,
);
