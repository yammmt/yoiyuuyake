import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./globals.css";
import Home from "./page";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("アプリケーションの表示先が見つかりません。");
}

createRoot(rootElement).render(
  <StrictMode>
    <Home />
  </StrictMode>,
);
